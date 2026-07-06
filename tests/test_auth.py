def auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def test_register_returns_user_without_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "New@Example.com", "password": "sup3r-secure-pw", "display_name": "New"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"  # normalized to lowercase
    assert "password" not in body and "password_hash" not in body


def test_register_duplicate_email_conflicts(client, registered_user):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": registered_user["email"].upper(),
            "password": "another-password",
            "display_name": "Impostor",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_login_returns_token_pair(token_pair):
    assert token_pair["access_token"]
    assert token_pair["refresh_token"]
    assert token_pair["token_type"] == "bearer"
    assert token_pair["expires_in"] == 15 * 60


def test_login_wrong_password_is_rejected(client, registered_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_email_gets_same_error_as_wrong_password(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "whatever-pw"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_me_requires_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_token"


def test_me_rejects_garbage_token(client):
    response = client.get("/api/v1/auth/me", headers=auth_header("not.a.jwt"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_me_returns_current_user(client, registered_user, token_pair):
    response = client.get("/api/v1/auth/me", headers=auth_header(token_pair["access_token"]))
    assert response.status_code == 200
    assert response.json()["email"] == registered_user["email"]


def test_refresh_rotates_tokens(client, token_pair):
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": token_pair["refresh_token"]}
    )
    assert response.status_code == 200
    new_pair = response.json()
    assert new_pair["refresh_token"] != token_pair["refresh_token"]

    # The new access token works.
    me = client.get("/api/v1/auth/me", headers=auth_header(new_pair["access_token"]))
    assert me.status_code == 200


def test_used_refresh_token_is_rejected(client, token_pair):
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": token_pair["refresh_token"]})
    assert first.status_code == 200

    replay = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": token_pair["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_refresh_token"


def test_reuse_detection_revokes_the_whole_family(client, token_pair):
    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": token_pair["refresh_token"]}
    ).json()

    # Replaying the old token trips reuse detection...
    replay = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": token_pair["refresh_token"]}
    )
    assert replay.status_code == 401

    # ...which revokes the rotated (still-unused) token too.
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert response.status_code == 401


def test_logout_revokes_refresh_token(client, token_pair):
    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": token_pair["refresh_token"]},
        headers=auth_header(token_pair["access_token"]),
    )
    assert response.status_code == 204

    refresh = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": token_pair["refresh_token"]}
    )
    assert refresh.status_code == 401


def test_unknown_refresh_token_is_rejected(client, token_pair):
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "made-up-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"
