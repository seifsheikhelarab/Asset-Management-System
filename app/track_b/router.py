import uuid
from datetime import UTC, date, datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import select

from app.core.rate_limit import limiter
from app.deps import AuthDep, SessionDep
from app.models import Asset, AssetType
from app.schemas import AssetCreate
from app.track_b.chains import (
    EnrichmentResult,
    QueryFilters,
    RiskAssessment,
    enrich_prompt,
    query_prompt,
    report_prompt,
    risk_prompt,
)
from app.track_b.llm import get_llm

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)).date()
    except (ValueError, TypeError):
        return None


def _asset_summary(asset: Asset) -> dict:
    return {
        "id": str(asset.id),
        "type": asset.type,
        "value": asset.value,
        "status": asset.status,
        "first_seen": asset.first_seen.isoformat(),
        "last_seen": asset.last_seen.isoformat(),
        "source": asset.source,
        "tags": asset.tags,
        "metadata": asset.extra_data,
    }


class RiskAssessmentRequest(BaseModel):
    asset_ids: list[uuid.UUID]


class QueryResponse(BaseModel):
    filters: QueryFilters
    explanation: str
    total: int
    assets: list[dict]


@router.post("/query")
@limiter.limit("10/minute")
def nl_query(
    request: Request,
    session: SessionDep,
    _auth: AuthDep,
    question: str = Query(..., description="Natural language question about assets"),
) -> QueryResponse:
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    llm = get_llm()
    chain = query_prompt | llm.with_structured_output(QueryFilters)
    try:
        filters = cast(QueryFilters, chain.invoke({"question": question}))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    query = select(Asset).where(Asset.org_id == _auth.org_id)
    if filters.type:
        query = query.where(Asset.type == filters.type)
    if filters.status:
        query = query.where(Asset.status == filters.status)
    if filters.tag:
        pattern = f'%"{filters.tag}"%'
        cond = text("CAST(tags AS TEXT) LIKE :tag")
        query = query.where(cond.bindparams(tag=pattern))
    if filters.search:
        query = query.where(
            text("LOWER(value) LIKE :q").bindparams(q=f"%{filters.search.lower()}%")
        )
    if filters.expired:
        query = query.where(Asset.type == AssetType.certificate)

    items = list(session.exec(query).all())

    if filters.expired:
        today = datetime.now(UTC).date()
        items = [
            a
            for a in items
            if isinstance(a.extra_data, dict)
            and "expires" in a.extra_data
            and (expires := _parse_date(a.extra_data["expires"])) is not None
            and expires < today
        ]

    return QueryResponse(
        filters=filters,
        explanation=filters.explanation,
        total=len(items),
        assets=[_asset_summary(a) for a in items],
    )


class RiskResponse(BaseModel):
    assessment: RiskAssessment
    assets_reviewed: list[dict]


@router.post("/risk")
@limiter.limit("10/minute")
def risk_assessment(
    request: Request,
    body: RiskAssessmentRequest,
    session: SessionDep,
    _auth: AuthDep,
) -> RiskResponse:
    if not body.asset_ids:
        raise HTTPException(status_code=400, detail="At least one asset_id required")

    id_col: Any = Asset.id
    assets = session.exec(
        select(Asset).where(id_col.in_(body.asset_ids), Asset.org_id == _auth.org_id)
    ).all()

    if not assets:
        raise HTTPException(status_code=404, detail="No assets found for given IDs")

    asset_data = "\n\n".join(
        f"Asset {a.value} ({a.type}): status={a.status}, "
        f"tags={a.tags}, metadata={a.extra_data}"
        for a in assets
    )

    llm = get_llm()
    chain = risk_prompt | llm.with_structured_output(RiskAssessment)
    try:
        assessment = cast(RiskAssessment, chain.invoke({"assets": asset_data}))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    return RiskResponse(
        assessment=assessment,
        assets_reviewed=[_asset_summary(a) for a in assets],
    )


class EnrichResponse(BaseModel):
    enrichment: EnrichmentResult
    original_asset: dict


@router.post("/enrich")
@limiter.limit("10/minute")
def enrich_asset(
    request: Request,
    asset: AssetCreate,
    _auth: AuthDep,
) -> EnrichResponse:
    asset_data = asset.model_dump_json(indent=2)

    llm = get_llm()
    chain = enrich_prompt | llm.with_structured_output(EnrichmentResult)
    try:
        enrichment = cast(EnrichmentResult, chain.invoke({"asset_data": asset_data}))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    return EnrichResponse(
        enrichment=enrichment,
        original_asset=asset.model_dump(),
    )


class ReportResponse(BaseModel):
    report: str
    total_assets: int


@router.post("/report")
@limiter.limit("5/minute")
def generate_report(
    request: Request,
    session: SessionDep,
    _auth: AuthDep,
    asset_type: str | None = Query(None, description="Filter by asset type"),
    status: str | None = Query(None, description="Filter by status"),
    tag: str | None = Query(None, description="Filter by tag"),
    search: str | None = Query(None, description="Search in asset value"),
) -> ReportResponse:
    query = select(Asset).where(Asset.org_id == _auth.org_id)

    if asset_type is not None:
        query = query.where(Asset.type == asset_type)
    if status is not None:
        query = query.where(Asset.status == status)
    if tag is not None:
        pattern = f'%"{tag}"%'
        cond = text("CAST(tags AS TEXT) LIKE :tag")
        query = query.where(cond.bindparams(tag=pattern))
    if search is not None:
        query = query.where(
            text("LOWER(value) LIKE :q").bindparams(q=f"%{search.lower()}%")
        )

    assets = list(session.exec(query).all())
    if not assets:
        raise HTTPException(status_code=404, detail="No assets match the given filters")

    asset_data = "\n\n".join(
        f"Asset {a.value} ({a.type}): status={a.status}, tags={a.tags}, "
        f"source={a.source}, metadata={a.extra_data}"
        for a in assets[:100]
    )

    total_note = ""
    if len(assets) > 100:
        total_note = (
            f"\n\n(Report based on first 100 of {len(assets)} matching assets.)"
        )

    llm = get_llm()
    chain = report_prompt | llm
    try:
        response = chain.invoke({"assets": asset_data + total_note})
        raw = response.content if hasattr(response, "content") else str(response)
        report_text = str(raw)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    return ReportResponse(report=report_text, total_assets=len(assets))
