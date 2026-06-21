from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.core.auth import AuthContext, require_admin, verify_auth
from app.core.db import get_session

SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(verify_auth)]
AdminDep = Annotated[AuthContext, Depends(require_admin)]
