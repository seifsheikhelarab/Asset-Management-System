from datetime import UTC, datetime, timedelta

import pytest

from app.core.auth import AuthContext, Role
from app.core.auth import verify_auth as _verify_auth
from app.main import app


@pytest.mark.anyio
async def test_create_asset(client, setup_db):
    resp = await client.post(
        "/assets/",
        json={
            "type": "domain",
            "value": "test.com",
            "source": "manual",
            "tags": ["test"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "domain"
    assert data["value"] == "test.com"
    assert data["status"] == "active"


@pytest.mark.anyio
async def test_list_assets(client, seeded_db):
    resp = await client.get("/assets/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.anyio
async def test_filter_by_type(client, seeded_db):
    resp = await client.get("/assets/?type=domain")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


@pytest.mark.anyio
async def test_filter_by_status(client, seeded_db):
    resp = await client.get("/assets/?status=stale")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["value"] == "blog.example.com"


@pytest.mark.anyio
async def test_filter_by_tag(client, seeded_db):
    resp = await client.get("/assets/?tag=prod")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


@pytest.mark.anyio
async def test_search_by_value(client, seeded_db):
    resp = await client.get("/assets/?q=blog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


@pytest.mark.anyio
async def test_get_asset(client, seeded_db):
    resp = await client.get("/assets/")
    asset_id = resp.json()["items"][0]["id"]

    resp = await client.get(f"/assets/{asset_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == asset_id


@pytest.mark.anyio
async def test_get_asset_not_found(client, setup_db):
    resp = await client.get("/assets/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_asset(client, seeded_db):
    resp = await client.get("/assets/")
    asset_id = resp.json()["items"][0]["id"]

    resp = await client.put(
        f"/assets/{asset_id}", json={"status": "stale", "tags": ["updated"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stale"
    assert "updated" in data["tags"]


@pytest.mark.anyio
async def test_delete_asset(client, seeded_db):
    resp = await client.get("/assets/")
    asset_id = resp.json()["items"][0]["id"]

    resp = await client.delete(f"/assets/{asset_id}")
    assert resp.status_code == 204

    resp = await client.get("/assets/")
    assert resp.json()["total"] == 2


@pytest.mark.anyio
async def test_bulk_import_dedup(client, seeded_db):
    existing = await client.get("/assets/")
    existing_count = existing.json()["total"]

    resp = await client.post(
        "/assets/bulk-import",
        json=[{"type": "domain", "value": "example.com", "source": "rescan"}],
    )
    assert resp.status_code == 201
    result = resp.json()
    assert result["created"] == 0
    assert result["updated"] == 1

    final = await client.get("/assets/")
    assert final.json()["total"] == existing_count


@pytest.mark.anyio
async def test_bulk_import_creates(client, seeded_db):
    resp = await client.post(
        "/assets/bulk-import",
        json=[{"type": "technology", "value": "nginx/1.25", "source": "scan"}],
    )
    assert resp.status_code == 201
    result = resp.json()
    assert result["created"] == 1
    assert result["updated"] == 0


@pytest.mark.anyio
async def test_pagination_defaults(client, seeded_db):
    resp = await client.get("/assets/?page_size=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] == 3
    assert data["page"] == 1


@pytest.mark.anyio
async def test_bulk_import_reactivates_stale(client, seeded_db):
    resp = await client.post(
        "/assets/bulk-import",
        json=[{"type": "subdomain", "value": "blog.example.com", "source": "rescan"}],
    )
    assert resp.status_code == 201
    assert resp.json()["updated"] == 1

    resp = await client.get("/assets/?status=active")
    items = resp.json()["items"]
    assert any(a["value"] == "blog.example.com" for a in items)


@pytest.mark.anyio
async def test_filter_expired_certificates(client, setup_db):
    await client.post(
        "/assets/",
        json={
            "type": "certificate",
            "value": "CN=expired.example.com",
            "extra_data": {"expires": "2020-01-01"},
            "source": "scan",
        },
    )
    await client.post(
        "/assets/",
        json={
            "type": "certificate",
            "value": "CN=valid.example.com",
            "extra_data": {"expires": "2099-01-01"},
            "source": "scan",
        },
    )

    resp = await client.get("/assets/?expired=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["value"] == "CN=expired.example.com"


@pytest.mark.anyio
async def test_filter_expiring_soon_certificates(client, setup_db):
    future = (datetime.now(UTC) + timedelta(days=15)).strftime("%Y-%m-%d")
    await client.post(
        "/assets/",
        json={
            "type": "certificate",
            "value": "CN=expiring.example.com",
            "extra_data": {"expires": future},
            "source": "scan",
        },
    )
    await client.post(
        "/assets/",
        json={
            "type": "certificate",
            "value": "CN=valid.example.com",
            "extra_data": {"expires": "2099-01-01"},
            "source": "scan",
        },
    )

    resp = await client.get("/assets/?expiring_soon=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert "expiring" in data["items"][0]["value"]


@pytest.mark.anyio
async def test_org_isolation(client, setup_db):
    app.dependency_overrides[_verify_auth] = lambda: AuthContext(
        principal="org_a_user", role=Role.admin, org_id="org_a"
    )
    try:
        await client.post(
            "/assets/",
            json={"type": "domain", "value": "org-a-only.com", "source": "scan"},
        )
        await client.post(
            "/assets/",
            json={"type": "domain", "value": "org-a-second.com", "source": "scan"},
        )

        resp = await client.get("/assets/")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

        app.dependency_overrides[_verify_auth] = lambda: AuthContext(
            principal="org_b_user", role=Role.admin, org_id="org_b"
        )

        resp = await client.get("/assets/")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
    finally:
        app.dependency_overrides[_verify_auth] = lambda: AuthContext(
            principal="test", role=Role.admin, org_id="default"
        )
