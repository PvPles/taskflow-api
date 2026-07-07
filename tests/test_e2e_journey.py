"""End-to-end journey test.

One flow that exercises the whole system the way a real client would, proving
the pieces work together (auth -> projects -> members -> tasks -> transitions
-> comments -> pagination -> deletion). The per-module tests cover edge cases;
this covers integration. Passes on both the SQLite fast path and Postgres.
"""

API = "/api/v1"


def _register_and_login(client, email: str, name: str) -> dict:
    reg = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "journey-pw-123", "display_name": name},
    )
    assert reg.status_code == 201, reg.text
    login = client.post(f"{API}/auth/login", json={"email": email, "password": "journey-pw-123"})
    assert login.status_code == 200, login.text
    return {
        "id": reg.json()["id"],
        "email": email,
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }


def test_full_user_journey(client):
    # 1. Two users sign up and log in.
    owner = _register_and_login(client, "e2e-owner@example.com", "Owner")
    member = _register_and_login(client, "e2e-member@example.com", "Member")

    # 2. Owner creates a project and adds the second user as a member.
    project = client.post(
        f"{API}/projects",
        json={"name": "Launch", "description": "the big one"},
        headers=owner["headers"],
    )
    assert project.status_code == 201, project.text
    pid = project.json()["id"]

    added = client.post(
        f"{API}/projects/{pid}/members",
        json={"email": member["email"]},
        headers=owner["headers"],
    )
    assert added.status_code == 201
    roles = {m["email"]: m["is_owner"] for m in added.json()}
    assert roles == {"e2e-owner@example.com": True, "e2e-member@example.com": False}

    # The member can now see the project in their own list.
    mine = client.get(f"{API}/projects", headers=member["headers"])
    assert [p["id"] for p in mine.json()] == [pid]

    # 3. The member creates several tasks; one is assigned to the owner.
    task_ids = []
    for i in range(5):
        body = {"title": f"task-{i}"}
        if i == 0:
            body["assignee_id"] = owner["id"]  # owner is implicitly a member
        r = client.post(f"{API}/projects/{pid}/tasks", json=body, headers=member["headers"])
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "todo"
        task_ids.append(r.json()["id"])

    assigned = client.get(f"{API}/tasks/{task_ids[0]}", headers=member["headers"])
    assert assigned.json()["assignee_id"] == owner["id"]

    # 4. Move one task through its lifecycle, and confirm the illegal jump fails.
    target = task_ids[0]

    def move(status: str):
        return client.patch(
            f"{API}/tasks/{target}", json={"status": status}, headers=owner["headers"]
        )

    assert move("in_progress").status_code == 200
    assert move("done").status_code == 200
    blocked = move("in_progress")  # done -> in_progress is forbidden
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "invalid_status_transition"
    assert move("todo").status_code == 200  # reopen makes it legal again
    assert move("in_progress").status_code == 200

    # 5. Both users comment on a task; comments list in creation order.
    comments_url = f"{API}/tasks/{target}/comments"
    assert (
        client.post(
            comments_url, json={"body": "starting this"}, headers=member["headers"]
        ).status_code
        == 201
    )
    assert (
        client.post(comments_url, json={"body": "looks good"}, headers=owner["headers"]).status_code
        == 201
    )
    listed = client.get(comments_url, headers=member["headers"])
    assert [c["body"] for c in listed.json()] == ["starting this", "looks good"]

    # 6. Walk the task list with cursor pagination - every task once, no repeats.
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        assert pages < 10, "pagination did not terminate"
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = client.get(
            f"{API}/projects/{pid}/tasks", params=params, headers=member["headers"]
        ).json()
        seen.extend(t["id"] for t in page["items"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 3  # 2 + 2 + 1
    assert sorted(seen) == sorted(task_ids)

    # 7. Clean up: the task creator deletes a task, the owner deletes the project.
    assert client.delete(f"{API}/tasks/{task_ids[1]}", headers=member["headers"]).status_code == 204

    assert client.delete(f"{API}/projects/{pid}", headers=owner["headers"]).status_code == 204
    # Project (and its cascade) is gone.
    assert client.get(f"{API}/projects/{pid}", headers=owner["headers"]).status_code == 404
    assert client.get(f"{API}/tasks/{target}", headers=owner["headers"]).status_code == 404
