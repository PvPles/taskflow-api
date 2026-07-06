"""Test fixtures.

By default tests run against in-memory SQLite (fast, no services needed).
Set TEST_DATABASE_URL to a Postgres URL to run the same suite as integration
tests against a real database - that's what CI does.
"""

import os

os.environ.setdefault(
    "TASKFLOW_JWT_SECRET", "test-secret-not-for-production-padded-to-32-bytes-plus"
)
# Rate limiting is exercised by its own test (which switches it on); leaving
# it on globally would make unrelated tests order-dependent.
os.environ.setdefault("TASKFLOW_RATE_LIMIT_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")

if TEST_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, connection_record):
        # SQLite ships with foreign keys off; turn them on so ON DELETE
        # CASCADE behaves like Postgres does.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

else:
    engine = create_engine(TEST_DATABASE_URL)

TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def create_user(client):
    """Factory: registers + logs in a user, returns auth headers and profile."""

    def _create(email: str, display_name: str = "User", password: str = "password-123!"):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": display_name},
        )
        assert response.status_code == 201, response.text
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        user = client.get("/api/v1/auth/me", headers=headers).json()
        return {"headers": headers, "user": user}

    return _create


@pytest.fixture()
def registered_user(client):
    payload = {
        "email": "spyro@example.com",
        "password": "sup3r-secure-pw",
        "display_name": "Spyro",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload


@pytest.fixture()
def token_pair(client, registered_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()
