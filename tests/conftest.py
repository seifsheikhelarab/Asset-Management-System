import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["TESTING"] = "1"

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.auth import AuthContext, Role, verify_auth
from app.core.cache import clear as clear_cache
from app.core.db import get_session
from app.main import app
from app.models import Asset

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def _set_fk_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def override_get_session():
    with Session(test_engine) as session:
        yield session


def override_verify_auth():
    return AuthContext(principal="test", role=Role.admin)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def setup_db():
    clear_cache()
    SQLModel.metadata.create_all(test_engine)
    yield
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
async def client():
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[verify_auth] = override_verify_auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_db(sample_assets):
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        for data in sample_assets.values():
            session.add(Asset(**data))
        session.commit()
    yield
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def sample_assets():
    return {
        "domain_root": {
            "type": "domain",
            "value": "example.com",
            "status": "active",
            "source": "scan",
            "tags": ["root"],
            "extra_data": {},
        },
        "sub_api": {
            "type": "subdomain",
            "value": "api.example.com",
            "status": "active",
            "source": "scan",
            "tags": ["prod", "api"],
            "extra_data": {},
        },
        "sub_blog": {
            "type": "subdomain",
            "value": "blog.example.com",
            "status": "stale",
            "source": "import",
            "tags": ["blog"],
            "extra_data": {},
        },
    }
