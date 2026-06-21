from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    api_key: str
    role: str = "viewer"
    org_id: str = "default"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token")
def create_token(body: TokenRequest) -> TokenResponse:
    if body.api_key != settings.auth_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    payload = {
        "sub": f"user_{body.org_id}",
        "role": body.role,
        "org_id": body.org_id,
        "exp": datetime.now(UTC) + timedelta(hours=24),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return TokenResponse(access_token=token)
