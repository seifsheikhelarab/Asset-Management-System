from enum import StrEnum

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


class Role(StrEnum):
    admin = "admin"
    viewer = "viewer"


class AuthContext(BaseModel):
    principal: str
    role: Role
    org_id: str = settings.default_org_id


def _decode_jwt(token: str) -> AuthContext | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},
        )
        return AuthContext(
            principal=payload.get("sub", "unknown"),
            role=Role(payload.get("role", Role.viewer)),
            org_id=payload.get("org_id", settings.default_org_id),
        )
    except jwt.PyJWTError:
        return None


def verify_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    if credentials is not None:
        token = credentials.credentials
    else:
        api_key = request.headers.get("x-api-key")
        if api_key is not None:
            token = api_key
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication",
            )

    if token == settings.auth_api_key:
        return AuthContext(principal="api_key", role=Role.admin)

    ctx = _decode_jwt(token)
    if ctx is not None:
        return ctx

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key or JWT",
    )


def require_admin(ctx: AuthContext = Depends(verify_auth)) -> AuthContext:
    if ctx.role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return ctx
