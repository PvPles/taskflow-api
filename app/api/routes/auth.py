from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPairOut, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_pair(access_token: str, refresh_token: str) -> TokenPairOut:
    settings = get_settings()
    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/register", status_code=201, response_model=UserOut, summary="Register a new account")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Create an account. Email is normalized to lowercase and must be unique."""
    return auth_service.register_user(db, body.email, body.password, body.display_name)


@router.post("/login", response_model=TokenPairOut, summary="Log in for an access + refresh pair")
def login(body: LoginIn, db: Session = Depends(get_db)):
    """Exchange credentials for a short-lived access token and a refresh token."""
    user = auth_service.authenticate_user(db, body.email, body.password)
    access_token, refresh_token = auth_service.issue_token_pair(db, user)
    return _token_pair(access_token, refresh_token)


@router.post("/refresh", response_model=TokenPairOut, summary="Rotate the refresh token")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    """Issue a fresh token pair and invalidate the presented refresh token.
    Replaying an already-used token revokes the whole family (reuse detection)."""
    _, access_token, refresh_token = auth_service.rotate_refresh_token(db, body.refresh_token)
    return _token_pair(access_token, refresh_token)


@router.post("/logout", status_code=204, summary="Revoke a refresh token")
def logout(
    body: RefreshIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke the given refresh token. Idempotent and never leaks whether it existed."""
    auth_service.revoke_refresh_token(db, current_user, body.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut, summary="Get the current user")
def me(current_user: User = Depends(get_current_user)):
    """Return the account for the presented access token."""
    return current_user
