import pytest


@pytest.fixture()
def setup(client, create_user):
    """A project with an owner, one member, and one outsider."""
    owner = create_user("owner@example.com", "Owner")
    member = create_user("member@example.com", "Member")
    outsider = create_user("outsider@example.com", "Outsider")
    project = client.post(
        "/api/v1/projects", json={"name": "Apollo"}, headers=owner["headers"]
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/members",
        json={"email": member["user"]["email"]},
        headers=owner["headers"],
    )
    return {"owner": owner, "member": member, "outsider": outsider, "project": project}


def make_task(client, setup, title="Fix the bug", by="member", **extra):
    response = client.post(
        f"/api/v1/projects/{setup['project']['id']}/tasks",
        json={"title": title, **extra},
        headers=setup[by]["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_new_task_starts_in_todo(client, setup):
    task = make_task(client, setup)
    assert task["status"] == "todo"
    assert task["created_by"] == setup["member"]["user"]["id"]


def test_assignee_must_be_a_member(client, setup):
    ok = make_task(client, setup, assignee_id=setup["owner"]["user"]["id"])
    assert ok["assignee_id"] == setup["owner"]["user"]["id"]

    response = client.post(
        f"/api/v1/projects/{setup['project']['id']}/tasks",
        json={"title": "Nope", "assignee_id": setup["outsider"]["user"]["id"]},
        headers=setup["member"]["headers"],
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assignee_not_member"


def test_status_transitions(client, setup):
    task = make_task(client, setup)
    url = f"/api/v1/tasks/{task['id']}"
    patch = lambda status: client.patch(
        url, json={"status": status}, headers=setup["member"]["headers"]
    )

    assert patch("in_progress").status_code == 200
    assert patch("done").status_code == 200

    # done -> in_progress is the transition the spec forbids.
    blocked = patch("in_progress")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "invalid_status_transition"

    assert patch("todo").status_code == 200  # reopen
    assert patch("in_progress").status_code == 200  # now allowed

    # Setting the current status again is a harmless no-op.
    assert patch("in_progress").status_code == 200

    unknown = patch("blocked")
    assert unknown.status_code == 422  # not a valid status at all


def test_outsider_cannot_see_or_touch_tasks(client, setup):
    task = make_task(client, setup)
    headers = setup["outsider"]["headers"]

    assert client.get(f"/api/v1/tasks/{task['id']}", headers=headers).status_code == 404
    assert (
        client.patch(
            f"/api/v1/tasks/{task['id']}", json={"title": "hacked"}, headers=headers
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/projects/{setup['project']['id']}/tasks", headers=headers).status_code
        == 404
    )


def test_delete_rules(client, setup):
    created_by_member = make_task(client, setup, by="member")
    created_by_owner = make_task(client, setup, by="owner")

    # A member cannot delete someone else's task...
    denied = client.delete(
        f"/api/v1/tasks/{created_by_owner['id']}", headers=setup["member"]["headers"]
    )
    assert denied.status_code == 403

    # ...but can delete their own, and the owner can delete anything.
    assert (
        client.delete(
            f"/api/v1/tasks/{created_by_member['id']}", headers=setup["member"]["headers"]
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/tasks/{created_by_owner['id']}", headers=setup["owner"]["headers"]
        ).status_code
        == 204
    )


def test_cursor_pagination_walks_all_tasks_without_overlap(client, setup):
    for i in range(25):
        make_task(client, setup, title=f"task-{i:02d}")

    url = f"/api/v1/projects/{setup['project']['id']}/tasks"
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        assert pages < 10, "cursor did not advance - would loop forever"
        params = {"limit": 10}
        if cursor:
            params["cursor"] = cursor
        page = client.get(url, params=params, headers=setup["member"]["headers"]).json()
        seen.extend(item["id"] for item in page["items"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert pages == 3  # 10 + 10 + 5
    assert len(seen) == 25
    assert len(set(seen)) == 25  # no duplicates across page boundaries


def test_task_list_is_newest_first_and_filterable(client, setup):
    first = make_task(client, setup, title="oldest")
    second = make_task(client, setup, title="newest")
    client.patch(
        f"/api/v1/tasks/{first['id']}",
        json={"status": "in_progress"},
        headers=setup["member"]["headers"],
    )

    url = f"/api/v1/projects/{setup['project']['id']}/tasks"
    everything = client.get(url, headers=setup["member"]["headers"]).json()
    assert [t["id"] for t in everything["items"]] == [second["id"], first["id"]]

    only_todo = client.get(
        url, params={"status": "todo"}, headers=setup["member"]["headers"]
    ).json()
    assert [t["id"] for t in only_todo["items"]] == [second["id"]]


def test_invalid_cursor_is_a_clean_400(client, setup):
    response = client.get(
        f"/api/v1/projects/{setup['project']['id']}/tasks",
        params={"cursor": "garbage!!"},
        headers=setup["member"]["headers"],
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cursor"


def test_unassign_by_setting_assignee_null(client, setup):
    task = make_task(client, setup, assignee_id=setup["member"]["user"]["id"])
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"assignee_id": None},
        headers=setup["member"]["headers"],
    )
    assert response.status_code == 200
    assert response.json()["assignee_id"] is None
