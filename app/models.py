import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


class AssetType(StrEnum):
    domain = "domain"
    subdomain = "subdomain"
    ip_address = "ip_address"
    service = "service"
    certificate = "certificate"
    technology = "technology"


class AssetStatus(StrEnum):
    active = "active"
    stale = "stale"
    archived = "archived"


class AssetBase(SQLModel):
    type: AssetType
    value: str
    status: AssetStatus = AssetStatus.active
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "import"
    tags: list[str] = Field(default=[], sa_type=JSON)
    extra_data: dict = Field(default={}, sa_type=JSON)


class Asset(AssetBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    org_id: str = Field(default="default", index=True)

    __table_args__ = (UniqueConstraint("type", "value", "org_id"),)


class RelationshipBase(SQLModel):
    source_asset_id: uuid.UUID = Field(foreign_key="asset.id", ondelete="CASCADE")
    target_asset_id: uuid.UUID = Field(foreign_key="asset.id", ondelete="CASCADE")
    relation_type: str


class Relationship(RelationshipBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    org_id: str = Field(default="default", index=True)
