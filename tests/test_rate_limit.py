from app.core.config import get_settings
from app.core.ratelimit import TokenBucket


def test_token_bucket_burst_and_refill():
    bucket = TokenBucket(capacity=2, refill_per_sec=1.0, now=0.0)

    assert bucket.allow(0.0) == (True, 0)
    assert bucket.allow(0.0) == (True, 0)

    allowed, retry_after = bucket.allow(0.0)  # burst exhausted
    assert allowed is False
    assert retry_after == 1

    assert bucket.allow(1.5)[0] is True  # refilled after 1.5s
    assert bucket.allow(1.5)[0] is False  # but only ~0.5 tokens remain


def test_token_bucket_never_exceeds_capacity():
    bucket = TokenBucket(capacity=3, refill_per_sec=100.0, now=0.0)
    bucket.allow(9999.0)  # huge idle time must not stockpile tokens
    assert bucket.tokens <= 3


def test_over_limit_requests_get_429_envelope(client, create_user, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_burst", 3)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)  # ~no refill mid-test

    user = create_user("limited@example.com")

    responses = [client.get("/api/v1/auth/me", headers=user["headers"]) for _ in range(5)]
    codes = [r.status_code for r in responses]
    assert codes[0] == 200
    assert 429 in codes

    limited = next(r for r in responses if r.status_code == 429)
    error = limited.json()["error"]
    assert error["code"] == "rate_limited"
    assert error["request_id"]  # 429s still carry a request ID
    assert "Retry-After" in limited.headers


def test_health_is_exempt_from_rate_limiting(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_burst", 1)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    codes = {client.get("/health").status_code for _ in range(10)}
    assert codes == {200}
