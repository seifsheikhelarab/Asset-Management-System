import pytest


@pytest.mark.anyio
async def test_create_relationship(client, seeded_db):
    resp = await client.get("/assets/")
    assets = resp.json()["items"]
    src = assets[0]["id"]
    tgt = assets[1]["id"]

    resp = await client.post(
        "/relationships/",
        json={
            "source_asset_id": src,
            "target_asset_id": tgt,
            "relation_type": "resolves_to",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_asset_id"] == src
    assert data["target_asset_id"] == tgt


@pytest.mark.anyio
async def test_list_relationships(client, seeded_db):
    resp = await client.get("/assets/")
    assets = resp.json()["items"]
    await client.post(
        "/relationships/",
        json={
            "source_asset_id": assets[0]["id"],
            "target_asset_id": assets[1]["id"],
            "relation_type": "resolves_to",
        },
    )

    resp = await client.get("/relationships/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


@pytest.mark.anyio
async def test_filter_relationships_by_asset(client, seeded_db):
    resp = await client.get("/assets/")
    assets = resp.json()["items"]
    await client.post(
        "/relationships/",
        json={
            "source_asset_id": assets[0]["id"],
            "target_asset_id": assets[1]["id"],
            "relation_type": "resolves_to",
        },
    )

    resp = await client.get(f"/relationships/?asset_id={assets[0]['id']}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.anyio
async def test_delete_relationship(client, seeded_db):
    resp = await client.get("/assets/")
    assets = resp.json()["items"]
    await client.post(
        "/relationships/",
        json={
            "source_asset_id": assets[0]["id"],
            "target_asset_id": assets[1]["id"],
            "relation_type": "resolves_to",
        },
    )

    resp = await client.get("/relationships/")
    rel_id = resp.json()["items"][0]["id"]

    resp = await client.delete(f"/relationships/{rel_id}")
    assert resp.status_code == 204

    resp = await client.get("/relationships/")
    assert resp.json()["total"] == 0


@pytest.mark.anyio
async def test_cascade_delete_asset_removes_relationships(client, seeded_db):
    resp = await client.get("/assets/")
    assets = resp.json()["items"]
    src = assets[0]["id"]
    tgt = assets[1]["id"]

    await client.post(
        "/relationships/",
        json={
            "source_asset_id": src,
            "target_asset_id": tgt,
            "relation_type": "resolves_to",
        },
    )

    resp = await client.get("/relationships/")
    assert resp.json()["total"] == 1

    await client.delete(f"/assets/{src}")

    resp = await client.get("/relationships/")
    assert resp.json()["total"] == 0
