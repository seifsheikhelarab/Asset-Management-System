import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func
from sqlmodel import select

from app.core.cache import build_key, get_cached, invalidate_org, set_cached
from app.core.rate_limit import limiter
from app.deps import AuthDep, SessionDep
from app.models import Asset, Relationship
from app.schemas import RelationshipCreate, RelationshipList, RelationshipRead

router = APIRouter(prefix="/relationships", tags=["relationships"])


def _to_read(rel: Relationship) -> RelationshipRead:
    return RelationshipRead(
        id=rel.id,
        source_asset_id=rel.source_asset_id,
        target_asset_id=rel.target_asset_id,
        relation_type=rel.relation_type,
        created_at=rel.created_at,
        org_id=rel.org_id,
    )


@router.get("/")
def list_relationships(
    _auth: AuthDep,
    session: SessionDep,
    asset_id: uuid.UUID | None = Query(None),
    relation_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> RelationshipList:
    query = select(Relationship).where(Relationship.org_id == _auth.org_id)

    if asset_id is not None:
        query = query.where(
            (Relationship.source_asset_id == asset_id)
            | (Relationship.target_asset_id == asset_id)
        )
    if relation_type is not None:
        query = query.where(Relationship.relation_type == relation_type)

    cache_key = build_key(
        _auth.org_id,
        "rels:list",
        asset_id=asset_id,
        relation_type=relation_type,
        page=page,
        page_size=page_size,
    )
    cached = get_cached(cache_key)
    if cached:
        return RelationshipList(**cached)

    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    offset = (page - 1) * page_size
    items = list(session.exec(query.offset(offset).limit(page_size)).all())

    result = RelationshipList(
        items=[_to_read(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    set_cached(cache_key, result.model_dump())
    return result


@router.post("/", status_code=201)
@limiter.limit("20/minute")
def create_relationship(
    request: Request,
    rel_in: RelationshipCreate,
    _auth: AuthDep,
    session: SessionDep,
) -> RelationshipRead:
    source = session.exec(
        select(Asset).where(
            Asset.id == rel_in.source_asset_id,
            Asset.org_id == _auth.org_id,
        )
    ).first()
    target = session.exec(
        select(Asset).where(
            Asset.id == rel_in.target_asset_id,
            Asset.org_id == _auth.org_id,
        )
    ).first()
    if not source or not target:
        raise HTTPException(status_code=404, detail="Source or target asset not found")

    relationship = Relationship.model_validate(rel_in)
    relationship.org_id = _auth.org_id
    session.add(relationship)
    session.commit()
    session.refresh(relationship)
    invalidate_org(_auth.org_id)
    return _to_read(relationship)


@router.delete("/{relationship_id}", status_code=204)
@limiter.limit("20/minute")
def delete_relationship(
    request: Request, relationship_id: uuid.UUID, _auth: AuthDep, session: SessionDep
):
    relationship = session.exec(
        select(Relationship).where(
            Relationship.id == relationship_id,
            Relationship.org_id == _auth.org_id,
        )
    ).first()
    if not relationship:
        raise HTTPException(status_code=404, detail="Relationship not found")
    session.delete(relationship)
    session.commit()
    invalidate_org(_auth.org_id)
