import uuid

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise APIError(401, "missing_token", "Authorization header is missing")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise APIError(401, "token_expired", "Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise APIError(401, "invalid_token", "Access token is invalid") from exc

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise APIError(401, "invalid_token", "Access token is invalid")

    # Exposed to the access-log middleware.
    request.state.user_id = str(user.id)
    return user
