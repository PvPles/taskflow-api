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


@router.post("/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    return auth_service.register_user(db, body.email, body.password, body.display_name)


@router.post("/login", response_model=TokenPairOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = auth_service.authenticate_user(db, body.email, body.password)
    access_token, refresh_token = auth_service.issue_token_pair(db, user)
    return _token_pair(access_token, refresh_token)


@router.post("/refresh", response_model=TokenPairOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    _, access_token, refresh_token = auth_service.rotate_refresh_token(db, body.refresh_token)
    return _token_pair(access_token, refresh_token)


@router.post("/logout", status_code=204)
def logout(
    body: RefreshIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    auth_service.revoke_refresh_token(db, current_user, body.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
