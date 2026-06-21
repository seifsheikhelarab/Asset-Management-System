from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlmodel import SQLModel

from app.core.db import engine
from app.core.rate_limit import limiter
from app.routers import assets, auth, relationships
from app.track_b.router import router as track_b_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="Asset Management System", lifespan=lifespan)

app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

app.include_router(assets.router)
app.include_router(auth.router)
app.include_router(relationships.router)
app.include_router(track_b_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
