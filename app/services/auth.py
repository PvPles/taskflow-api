import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError
from app.core.security import (
    create_access_token,
    ensure_utc,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User

logger = logging.getLogger("taskflow.auth")


def register_user(db: Session, email: str, password: str, display_name: str) -> User:
    email = email.strip().lower()
    user = User(email=email, password_hash=hash_password(password), display_name=display_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(409, "email_taken", "An account with this email already exists") from exc
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    # Identical response for unknown email and bad password (no enumeration).
    if user is None or not verify_password(password, user.password_hash):
        raise APIError(401, "invalid_credentials", "Invalid email or password")
    if not user.is_active:
        raise APIError(401, "invalid_credentials", "Invalid email or password")
    return user


def issue_token_pair(db: Session, user: User) -> tuple[str, str]:
    settings = get_settings()
    access_token = create_access_token(user.id)
    raw_refresh, token_hash = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    db.commit()
    return access_token, raw_refresh


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[User, str, str]:
    """Validate and rotate a refresh token, returning a fresh pair.

    An already-revoked token presented again trips reuse detection: all of the
    user's active tokens are revoked, since replay implies the token leaked.
    """
    now = datetime.now(UTC)
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if stored is None:
        raise APIError(401, "invalid_refresh_token", "Refresh token is invalid")

    if stored.revoked_at is not None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == stored.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
        logger.warning("refresh_token_reuse_detected", extra={"user_id": str(stored.user_id)})
        raise APIError(401, "invalid_refresh_token", "Refresh token is invalid")

    if ensure_utc(stored.expires_at) < now:
        raise APIError(401, "refresh_token_expired", "Refresh token has expired")

    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise APIError(401, "invalid_refresh_token", "Refresh token is invalid")

    access_token = create_access_token(user.id)
    raw_refresh, token_hash = generate_refresh_token()
    settings = get_settings()
    replacement = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
    )
    db.add(replacement)
    db.flush()
    stored.revoked_at = now
    stored.replaced_by_id = replacement.id
    db.commit()
    return user, access_token, raw_refresh


def revoke_refresh_token(db: Session, user: User, raw_token: str) -> None:
    """Revoke a refresh token; silent on unknown tokens to avoid an oracle."""
    stored = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(raw_token),
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    if stored is not None:
        stored.revoked_at = datetime.now(UTC)
        db.commit()
