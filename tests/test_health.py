from app.db.session import get_db
from app.main import app


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_db_reachable(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_db_down(client):
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("database is gone")

    def broken_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"


def test_every_response_carries_a_request_id(client):
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_client_supplied_request_id_is_echoed(client):
    response = client.get("/health", headers={"X-Request-ID": "my-trace-id"})
    assert response.headers["X-Request-ID"] == "my-trace-id"


def test_unknown_route_returns_error_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_validation_error_returns_envelope_with_details(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "short", "display_name": ""},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["request_id"]
    fields = {detail["field"] for detail in error["details"]}
    assert "body.email" in fields
    assert "body.password" in fields
