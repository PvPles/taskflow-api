import pytest


@pytest.fixture()
def owner(create_user):
    return create_user("owner@example.com", "Owner")


@pytest.fixture()
def member(create_user):
    return create_user("member@example.com", "Member")


@pytest.fixture()
def outsider(create_user):
    return create_user("outsider@example.com", "Outsider")


def make_project(client, user, name="Apollo"):
    response = client.post(
        "/api/v1/projects", json={"name": name, "description": "test"}, headers=user["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_projects(client, owner):
    project = make_project(client, owner)
    assert project["owner_id"] == owner["user"]["id"]

    listed = client.get("/api/v1/projects", headers=owner["headers"]).json()
    assert [p["id"] for p in listed] == [project["id"]]


def test_non_member_gets_404_not_403(client, owner, outsider):
    project = make_project(client, owner)
    response = client.get(f"/api/v1/projects/{project['id']}", headers=outsider["headers"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"


def test_owner_can_add_member_who_then_has_access(client, owner, member):
    project = make_project(client, owner)
    pid = project["id"]

    added = client.post(
        f"/api/v1/projects/{pid}/members",
        json={"email": member["user"]["email"]},
        headers=owner["headers"],
    )
    assert added.status_code == 201
    roles = {m["email"]: m["is_owner"] for m in added.json()}
    assert roles == {"owner@example.com": True, "member@example.com": False}

    assert client.get(f"/api/v1/projects/{pid}", headers=member["headers"]).status_code == 200
    # Member sees the project in their own list too.
    listed = client.get("/api/v1/projects", headers=member["headers"]).json()
    assert [p["id"] for p in listed] == [pid]


def test_add_member_error_cases(client, owner, member):
    pid = make_project(client, owner)["id"]
    add = lambda email: client.post(
        f"/api/v1/projects/{pid}/members", json={"email": email}, headers=owner["headers"]
    )

    assert add("ghost@example.com").status_code == 404
    assert add("ghost@example.com").json()["error"]["code"] == "user_not_found"

    assert add(member["user"]["email"]).status_code == 201
    duplicate = add(member["user"]["email"])
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "already_member"

    owner_self = add(owner["user"]["email"])
    assert owner_self.status_code == 409  # owner is already implicitly a member


def test_only_owner_can_update_and_delete(client, owner, member):
    pid = make_project(client, owner)["id"]
    client.post(
        f"/api/v1/projects/{pid}/members",
        json={"email": member["user"]["email"]},
        headers=owner["headers"],
    )

    denied = client.patch(
        f"/api/v1/projects/{pid}", json={"name": "Hijacked"}, headers=member["headers"]
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"

    renamed = client.patch(
        f"/api/v1/projects/{pid}", json={"name": "Artemis"}, headers=owner["headers"]
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Artemis"

    assert client.delete(f"/api/v1/projects/{pid}", headers=member["headers"]).status_code == 403
    assert client.delete(f"/api/v1/projects/{pid}", headers=owner["headers"]).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=owner["headers"]).status_code == 404


def test_remove_member(client, owner, member):
    pid = make_project(client, owner)["id"]
    client.post(
        f"/api/v1/projects/{pid}/members",
        json={"email": member["user"]["email"]},
        headers=owner["headers"],
    )

    removed = client.delete(
        f"/api/v1/projects/{pid}/members/{member['user']['id']}", headers=owner["headers"]
    )
    assert removed.status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=member["headers"]).status_code == 404

    again = client.delete(
        f"/api/v1/projects/{pid}/members/{member['user']['id']}", headers=owner["headers"]
    )
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "member_not_found"

    owner_removal = client.delete(
        f"/api/v1/projects/{pid}/members/{owner['user']['id']}", headers=owner["headers"]
    )
    assert owner_removal.status_code == 409
    assert owner_removal.json()["error"]["code"] == "cannot_remove_owner"
