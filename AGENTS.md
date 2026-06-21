# AGENTS.md — Asset Management System

## Project state

Built. Full FastAPI app with SQLModel, PostgreSQL. Two tracks: A (REST API) + B (LangChain AI layer).

## Commands

| Action | Command |
|---|---|
| Dev server | `fastapi dev` |
| Production | `fastapi run` |
| Package mgmt | `uv add ...` / `uv sync` |
| Lint | `ruff check .` |
| Format | `ruff format .` |
| Typecheck | `ty check` (not mypy, not `ty .`) |
| Tests | `uv run pytest -v` |
| Infra | `docker-compose up --build` |

`pyproject.toml` entrypoint: `[tool.fastapi] entrypoint = "app.main:app"`.

## Architecture

```
app/
├── main.py              # FastAPI entrypoint, lifespan creates tables
├── models.py            # SQLModel: Asset (6 types), Relationship
├── schemas.py           # Pydantic: AssetCreate, BulkImportItem, RelationshipCreate, etc.
├── deps.py              # SessionDep, AuthDep, AdminDep (Annotated type aliases)
├── core/
│   ├── config.py        # pydantic-settings
│   ├── db.py            # Engine + session factory
│   ├── auth.py          # JWT / API key + RBAC
│   ├── cache.py         # In-memory TTL cache
│   └── rate_limit.py    # slowapi limiter
├── routers/
│   ├── assets.py        # CRUD, list/filter/sort/paginate, bulk import, graph
│   └── relationships.py # Relationship CRUD
└── track_b/
    ├── router.py        # /analyze/query, /risk, /enrich, /report
    ├── llm.py           # ChatOpenAI factory, reads env LLM_API_KEY
    └── chains.py        # LangChain prompt templates + Pydantic output schemas
tests/
├── conftest.py          # SQLite engine (StaticPool), client fixture, seed data
├── test_assets.py
└── test_relationships.py
```

## FastAPI conventions (applied in this repo)

- `Annotated` for deps and query/body params (defined in `deps.py`)
- No `...` for required fields — omit the default
- Return type annotations (`-> AssetRead`) over `response_model`
- `APIRouter(prefix="/...", tags=["..."])` on the router, not `include_router()`
- `def` over `async def` unless async code is called
- Dependencies with `= None` defaults cause Python syntax error if they follow `Query()` params — deps must come **before** query params

## Key conventions & quirks

- **Auth:** all endpoints require auth. Override `verify_auth` in tests via `app.dependency_overrides`.
- **Rate limiting:** disabled during tests via `TESTING=1` env var check in `rate_limit.py`.
- **Bulk import** uses `BulkImportItem` schema (not `AssetCreate`) — supports optional `id` (string slug), `parent`, `covers` for relationship linking.
- **Relationship `ondelete="CASCADE"`** on `source_asset_id`/`target_asset_id` foreign keys. Tests enable via `PRAGMA foreign_keys=ON` event listener on the SQLite engine.
- **`extra_data`** (not `metadata`) to avoid shadowing SQLModel's `metadata`.
- **Dedup key:** `(type, value)` unique constraint at DB level.
- **Certificate expiry** checked in Python (after DB fetch) because JSONB extraction differs between Pg and SQLite.
- **bulk_import** uses `session.flush()` between records so the `slug_map` is populated before relationship creation.
- **`ty check`** errors can be suppressed with `# noqa: <error-code>`, but some SQLAlchemy-style instrumentation (e.g. `Asset.id.in_()`) needs an `id_col: Any = Asset.id` workaround.

## Testing

- `pytest`, in-memory SQLite, no external services needed.
- Fixtures: `client` (overrides deps), `setup_db` (create/drop tables), `seeded_db` (inserts 3 sample assets).
- The `@pytest.mark.anyio` decorator is required for all async test functions.
- Rate limiting is auto-disabled in tests.

## Edge cases verified

- Idempotent import (re-import updates `last_seen`, merges tags/metadata)
- Stale asset reactivation on re-sight
- Malformed records per-item error collection in bulk import
- Expired vs expiring-soon certificate filtering
- Multi-org isolation (query-level `org_id` scoping)
- Cascade delete (asset removal removes relationships)
