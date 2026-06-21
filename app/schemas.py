import uuid
from datetime import datetime

from sqlmodel import SQLModel

from app.models import AssetBase, AssetStatus, RelationshipBase


class AssetCreate(AssetBase): ...


class BulkImportItem(AssetBase):
    id: str | None = None
    parent: str | None = None
    covers: str | None = None


class AssetUpdate(SQLModel):
    value: str | None = None
    status: AssetStatus | None = None
    source: str | None = None
    tags: list[str] | None = None
    extra_data: dict | None = None


class AssetRead(AssetBase):
    id: uuid.UUID
    first_seen: datetime
    last_seen: datetime
    org_id: str


class AssetList(SQLModel):
    items: list[AssetRead]
    total: int
    page: int
    page_size: int


class RelationshipCreate(RelationshipBase): ...


class RelationshipRead(RelationshipBase):
    id: uuid.UUID
    created_at: datetime
    org_id: str


class RelationshipList(SQLModel):
    items: list[RelationshipRead]
    total: int
    page: int
    page_size: int


class AssetWithRelations(SQLModel):
    asset: AssetRead
    outgoing: list[RelationshipRead]
    incoming: list[RelationshipRead]


class BulkImportResult(SQLModel):
    created: int
    updated: int
    errors: list[dict]
