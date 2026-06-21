import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, text
from sqlmodel import select

from app.core.cache import build_key, get_cached, invalidate_org, set_cached
from app.core.rate_limit import limiter
from app.deps import AdminDep, AuthDep, SessionDep
from app.models import Asset, AssetStatus, AssetType, Relationship
from app.schemas import (
    AssetCreate,
    AssetList,
    AssetRead,
    AssetUpdate,
    AssetWithRelations,
    BulkImportItem,
    BulkImportResult,
    RelationshipRead,
)

router = APIRouter(prefix="/assets", tags=["assets"])

_SORTABLE_COLUMNS = frozenset(
    {
        "type",
        "value",
        "status",
        "source",
        "org_id",
        "first_seen",
        "last_seen",
    }
)


def _to_read(asset: Asset) -> AssetRead:
    return AssetRead(
        id=asset.id,
        type=asset.type,
        value=asset.value,
        status=asset.status,
        first_seen=asset.first_seen,
        last_seen=asset.last_seen,
        source=asset.source,
        tags=asset.tags,
        extra_data=asset.extra_data,
        org_id=asset.org_id,
    )


@router.get("/")
def list_assets(
    _auth: AuthDep,
    session: SessionDep,
    type: AssetType | None = Query(None),
    status: AssetStatus | None = Query(None),
    tag: str | None = Query(None),
    q: str | None = Query(None, description="Search in value"),
    expired: bool | None = Query(None, description="Filter expired certificates"),
    expiring_soon: bool | None = Query(
        None, description="Filter certificates expiring within 30 days"
    ),
    sort_by: str = Query("last_seen"),
    sort_desc: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AssetList:
    query = select(Asset).where(Asset.org_id == _auth.org_id)

    if type is not None:
        query = query.where(Asset.type == type)
    if status is not None:
        query = query.where(Asset.status == status)
    if tag is not None:
        pattern = f'%"{tag}"%'
        cond = text("CAST(tags AS TEXT) LIKE :tag")
        query = query.where(cond.bindparams(tag=pattern))
    if q is not None:
        query = query.where(text("LOWER(value) LIKE :q").bindparams(q=f"%{q.lower()}%"))

    if expired is not None or expiring_soon is not None:
        query = query.where(Asset.type == AssetType.certificate)

    if sort_by not in _SORTABLE_COLUMNS:
        sort_by = "last_seen"
    sort_col = cast(Any, getattr(Asset, sort_by, Asset.last_seen))
    query = query.order_by(sort_col.desc() if sort_desc else sort_col.asc())

    cache_key = build_key(
        _auth.org_id,
        "assets:list",
        type=type,
        status=status,
        tag=tag,
        q=q,
        expired=expired,
        expiring_soon=expiring_soon,
        sort_by=sort_by,
        sort_desc=sort_desc,
        page=page,
        page_size=page_size,
    )
    cached = get_cached(cache_key)
    if cached:
        return AssetList(**cached)

    if expired is not None or expiring_soon is not None:
        all_items = cast(list[Asset], session.exec(query).all())
        today = datetime.now(UTC).date()
        filtered: list[Asset] = []
        for item in all_items:
            expires_str = item.extra_data.get("expires")
            if not expires_str:
                continue
            try:
                expires_date = datetime.fromisoformat(str(expires_str)).date()
            except (ValueError, TypeError):
                continue
            if expired and expires_date < today:
                filtered.append(item)
            elif expiring_soon and today <= expires_date <= today + timedelta(days=30):
                filtered.append(item)
        total = len(filtered)
        offset = (page - 1) * page_size
        items = filtered[offset : offset + page_size]
    else:
        total = session.exec(select(func.count()).select_from(query.subquery())).one()
        offset = (page - 1) * page_size
        paginated = query.offset(offset).limit(page_size)
        items = cast(list[Asset], session.exec(paginated).all())

    result = AssetList(
        items=[_to_read(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    set_cached(cache_key, result.model_dump())
    return result


@router.get("/{asset_id}")
def get_asset(asset_id: uuid.UUID, _auth: AuthDep, session: SessionDep) -> AssetRead:
    cache_key = build_key(_auth.org_id, "assets:get", asset_id=str(asset_id))
    cached = get_cached(cache_key)
    if cached:
        return AssetRead(**cached)

    asset = session.exec(
        select(Asset).where(Asset.id == asset_id, Asset.org_id == _auth.org_id)
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = _to_read(asset)
    set_cached(cache_key, result.model_dump())
    return result


@router.get("/{asset_id}/graph")
def get_asset_graph(
    asset_id: uuid.UUID, _auth: AuthDep, session: SessionDep
) -> AssetWithRelations:
    cache_key = build_key(_auth.org_id, "assets:graph", asset_id=str(asset_id))
    cached = get_cached(cache_key)
    if cached:
        return AssetWithRelations(**cached)

    asset = session.exec(
        select(Asset).where(Asset.id == asset_id, Asset.org_id == _auth.org_id)
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    outgoing = [
        RelationshipRead(
            id=r.id,
            source_asset_id=r.source_asset_id,
            target_asset_id=r.target_asset_id,
            relation_type=r.relation_type,
            created_at=r.created_at,
            org_id=r.org_id,
        )
        for r in session.exec(
            select(Relationship).where(
                Relationship.source_asset_id == asset_id,
                Relationship.org_id == _auth.org_id,
            )
        ).all()
    ]
    incoming = [
        RelationshipRead(
            id=r.id,
            source_asset_id=r.source_asset_id,
            target_asset_id=r.target_asset_id,
            relation_type=r.relation_type,
            created_at=r.created_at,
            org_id=r.org_id,
        )
        for r in session.exec(
            select(Relationship).where(
                Relationship.target_asset_id == asset_id,
                Relationship.org_id == _auth.org_id,
            )
        ).all()
    ]

    result = AssetWithRelations(
        asset=_to_read(asset),
        outgoing=outgoing,
        incoming=incoming,
    )
    set_cached(cache_key, result.model_dump())
    return result


@router.post("/", status_code=201)
@limiter.limit("20/minute")
def create_asset(
    request: Request,
    asset_in: AssetCreate,
    _auth: AuthDep,
    session: SessionDep,
) -> AssetRead:
    existing = session.exec(
        select(Asset).where(
            Asset.type == asset_in.type,
            Asset.value == asset_in.value,
            Asset.org_id == _auth.org_id,
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Asset with this type and value already exists in this org",
        )

    asset = Asset.model_validate(asset_in)
    asset.org_id = _auth.org_id
    session.add(asset)
    session.commit()
    session.refresh(asset)
    invalidate_org(_auth.org_id)
    return _to_read(asset)


@router.put("/{asset_id}")
@limiter.limit("20/minute")
def update_asset(
    request: Request,
    asset_id: uuid.UUID,
    asset_in: AssetUpdate,
    _auth: AuthDep,
    session: SessionDep,
) -> AssetRead:
    asset = session.exec(
        select(Asset).where(Asset.id == asset_id, Asset.org_id == _auth.org_id)
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    update_data = asset_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(asset, key, value)
    asset.last_seen = datetime.now(UTC)
    session.add(asset)
    session.commit()
    session.refresh(asset)
    invalidate_org(_auth.org_id)
    return _to_read(asset)


@router.delete("/{asset_id}", status_code=204)
@limiter.limit("20/minute")
def delete_asset(
    request: Request, asset_id: uuid.UUID, _auth: AuthDep, session: SessionDep
):
    asset = session.exec(
        select(Asset).where(Asset.id == asset_id, Asset.org_id == _auth.org_id)
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    session.delete(asset)
    session.commit()
    invalidate_org(_auth.org_id)


_MAX_BULK_SIZE = 10000


@router.post("/bulk-import", status_code=201)
@limiter.limit("5/minute")
def bulk_import(
    request: Request,
    assets_in: list[BulkImportItem],
    _auth: AdminDep,
    session: SessionDep,
) -> BulkImportResult:
    if len(assets_in) > _MAX_BULK_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"Bulk import limited to {_MAX_BULK_SIZE} records",
        )
    created = 0
    updated = 0
    errors: list[dict] = []
    slug_map: dict[str, uuid.UUID] = {}
    pending_rels: list[dict] = []

    for i, item in enumerate(assets_in):
        try:
            existing = session.exec(
                select(Asset).where(
                    Asset.type == item.type,
                    Asset.value == item.value,
                    Asset.org_id == _auth.org_id,
                )
            ).first()

            if existing:
                existing.last_seen = datetime.now(UTC)
                if existing.status == AssetStatus.stale:
                    existing.status = AssetStatus.active
                if item.tags:
                    existing.tags = list(set(existing.tags + item.tags))
                if item.extra_data:
                    existing.extra_data.update(item.extra_data)
                session.add(existing)
                session.flush()
                asset_id = existing.id
                updated += 1
            else:
                asset_data = item.model_dump(exclude={"id", "parent", "covers"})
                asset = Asset.model_validate(asset_data)
                asset.org_id = _auth.org_id
                session.add(asset)
                session.flush()
                asset_id = asset.id
                created += 1

            if item.id:
                slug_map[item.id] = asset_id

            if item.parent:
                pending_rels.append(
                    {
                        "child_slug": item.id,
                        "parent_slug": item.parent,
                        "type": "contains",
                    }
                )
            if item.covers:
                pending_rels.append(
                    {
                        "child_slug": item.covers,
                        "parent_slug": item.id,
                        "type": "covers",
                    }
                )
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    for rel in pending_rels:
        try:
            parent_id = slug_map.get(rel["parent_slug"])
            child_id = slug_map.get(rel["child_slug"])
            if parent_id and child_id:
                exists = session.exec(
                    select(Relationship).where(
                        Relationship.source_asset_id == parent_id,
                        Relationship.target_asset_id == child_id,
                        Relationship.relation_type == rel["type"],
                        Relationship.org_id == _auth.org_id,
                    )
                ).first()
                if not exists:
                    relationship = Relationship(
                        source_asset_id=parent_id,
                        target_asset_id=child_id,
                        relation_type=rel["type"],
                        org_id=_auth.org_id,
                    )
                    session.add(relationship)
        except Exception:
            pass

    session.commit()
    invalidate_org(_auth.org_id)
    return BulkImportResult(created=created, updated=updated, errors=errors)
