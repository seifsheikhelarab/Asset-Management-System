# Asset Management System

A REST API for managing internet-facing assets — domains, subdomains, IP addresses, services, TLS certificates, and technologies — with deduplication, lifecycle tracking, and a relationship graph. Built as a module of the DarkAtlas Attack Surface Monitoring platform.

**Stack:** Python 3.14 · FastAPI · SQLModel · PostgreSQL

## Quick start

```bash
# Start everything (API + PostgreSQL)
docker-compose up --build

# API at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

## Local development

```bash
# Install dependencies
uv sync --all-extras

# Start PostgreSQL only
docker-compose up -d db

# Run dev server with hot-reload
fastapi dev
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://app:app@localhost:5432/assets` | Database connection string |
| `AUTH_API_KEY` | `change-me` | API key for authentication (X-API-Key header) |
| `JWT_SECRET` | `change-me` | Secret for JWT token verification |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `DEFAULT_ORG_ID` | `default` | Default organization ID for single-org deployments |

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

## API overview

All endpoints require authentication via `X-API-Key` header or `Authorization: Bearer <token>`.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/assets/` | Yes | List assets with filter, sort, pagination |
| POST | `/assets/` | Yes | Create a single asset |
| GET | `/assets/{id}` | Yes | Get asset by ID |
| PUT | `/assets/{id}` | Yes | Update asset fields |
| DELETE | `/assets/{id}` | Yes | Delete an asset |
| POST | `/assets/bulk-import` | Admin | Bulk import (upsert + dedup) |
| GET | `/assets/{id}/graph` | Yes | Get asset relationship graph |
| GET | `/relationships/` | Yes | List relationships |
| POST | `/relationships/` | Yes | Create a relationship |
| DELETE | `/relationships/{id}` | Yes | Delete a relationship |

### Query parameters for `GET /assets/`

| Param | Type | Description |
|---|---|---|
| `type` | enum | Filter: `domain`, `subdomain`, `ip_address`, `service`, `certificate`, `technology` |
| `status` | enum | Filter: `active`, `stale`, `archived` |
| `tag` | string | Filter assets with this tag |
| `q` | string | Search by value (case-insensitive contains) |
| `expired` | bool | Filter to expired certificates (requires `type=certificate`) |
| `expiring_soon` | bool | Filter to certificates expiring within 30 days |
| `sort_by` | string | Field to sort by (default: `last_seen`) |
| `sort_desc` | bool | Sort descending (default: `true`) |
| `page` | int | Page number, 1-indexed (default: 1) |
| `page_size` | int | Items per page, max 100 (default: 20) |

## Design decisions

- **SQLModel** over raw SQLAlchemy for idiomatic model definitions with Pydantic integration.
- **`extra_data`** instead of `metadata` to avoid shadowing SQLModel's class-level `metadata` attribute.
- **Composite upsert key** of `(type, value)` for deduplication, since assets are uniquely identified by their type + canonical value.
- **Metadata merge strategy:** when re-importing, the top-level `extra_data` dict is shallow-merged (new keys added, existing keys overwritten by the latest source). Tags are unioned and deduplicated.
- **Portable SQL** with `text()` expressions for tag and expiry filtering — works on both PostgreSQL and SQLite (test database).
- **Certificate expiry filtering** is performed in Python after fetching from the database, because JSONB field extraction syntax differs between PostgreSQL (`->>`) and SQLite, and expiry checks are typically run against a small subset of assets.
- **`StaticPool`** for SQLite test database to avoid thread-isolated in-memory databases (FastAPI's thread pool creates connections in different threads).
- **Multi-tenancy** is enforced at the query level — every endpoint filters by `org_id` derived from the authenticated principal's JWT or API key configuration.

### Entity-relationship note

The sample dataset shows a `parent` field on subdomains and a `covers` field on certificates. These are modeled as explicit entries in the `Relationship` table rather than columns on the `Asset` model, keeping the schema normalized and extensible.

## Running tests

```bash
uv run pytest
```

Tests use an in-memory SQLite database and require no external services. Rate limiting is automatically disabled during tests.

## Lint & typecheck

```bash
uv run ruff check .        # Lint
uv run ruff format .       # Format
uv run ty check app/       # Type checking
```

## Project structure

```
app/
├── main.py              # FastAPI app entrypoint
├── models.py            # SQLModel models (Asset, Relationship)
├── schemas.py           # Pydantic request/response schemas
├── deps.py              # Dependency type aliases (SessionDep, AuthDep, AdminDep)
├── core/
│   ├── config.py        # Settings via pydantic-settings
│   ├── db.py            # Database engine and session factory
│   ├── auth.py          # API key / JWT verification and RBAC
│   ├── cache.py         # In-memory TTL cache
│   └── rate_limit.py    # Rate limiting (slowapi)
└── routers/
    ├── assets.py        # Asset CRUD, list, bulk import, graph
    └── relationships.py # Relationship CRUD
tests/
├── conftest.py          # Fixtures (SQLite, client, seed data)
├── test_assets.py       # Asset CRUD, filter, pagination, dedup, org isolation
└── test_relationships.py
```

## Edge cases handled

- **Idempotent imports** — re-importing the same dataset updates `last_seen` and merges metadata/tags; no duplicates.
- **Conflicting metadata** — tags are unioned, metadata dicts are shallow-merged.
- **Re-appearing stale assets** — a stale asset seen again in an import is reactivated.
- **Malformed records** — each record in a bulk import is wrapped in try/except; bad records are collected in the error response without crashing the batch.
- **Pagination** — defaults to page 1, 20 items per page, capped at 100.
- **Certificate expiry** — endpoints support `expired` and `expiring_soon` filters, checking dates in `extra_data.expires`.
- **Multi-tenant isolation** — every query is scoped by `org_id` from the authenticated context.

## Assumptions

- Assets are uniquely identified by `(type, value)`. If two records share the same type and value, they are considered the same asset regardless of ID.
- Certificate expiry dates are stored as ISO date strings (`YYYY-MM-DD`) in the asset's `extra_data` under the key `expires`.
- "Expiring soon" means within 30 days from today.
- Authentication is required for all endpoints. API key users get admin role; JWT tokens carry role and org_id claims.
- Multi-tenant isolation is enforced at the query level.

## License

Internship acceptance task — DarkAtlas / Buguard.
