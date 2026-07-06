import pytest


@pytest.fixture()
def setup(client, create_user):
    owner = create_user("owner@example.com", "Owner")
    member = create_user("member@example.com", "Member")
    second = create_user("second@example.com", "Second")
    outsider = create_user("outsider@example.com", "Outsider")
    project = client.post(
        "/api/v1/projects", json={"name": "Apollo"}, headers=owner["headers"]
    ).json()
    for u in (member, second):
        client.post(
            f"/api/v1/projects/{project['id']}/members",
            json={"email": u["user"]["email"]},
            headers=owner["headers"],
        )
    task = client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        json={"title": "Discuss"},
        headers=owner["headers"],
    ).json()
    return {
        "owner": owner,
        "member": member,
        "second": second,
        "outsider": outsider,
        "task": task,
    }


def test_comment_create_and_list_in_order(client, setup):
    url = f"/api/v1/tasks/{setup['task']['id']}/comments"
    first = client.post(url, json={"body": "first!"}, headers=setup["member"]["headers"])
    assert first.status_code == 201
    client.post(url, json={"body": "second"}, headers=setup["owner"]["headers"])

    listed = client.get(url, headers=setup["second"]["headers"])
    assert listed.status_code == 200
    assert [c["body"] for c in listed.json()] == ["first!", "second"]


def test_outsider_cannot_comment_or_read(client, setup):
    url = f"/api/v1/tasks/{setup['task']['id']}/comments"
    headers = setup["outsider"]["headers"]
    assert client.post(url, json={"body": "hi"}, headers=headers).status_code == 404
    assert client.get(url, headers=headers).status_code == 404


def test_delete_rules(client, setup):
    url = f"/api/v1/tasks/{setup['task']['id']}/comments"
    comment = client.post(
        url, json={"body": "delete me"}, headers=setup["member"]["headers"]
    ).json()

    other_member = client.delete(
        f"/api/v1/comments/{comment['id']}", headers=setup["second"]["headers"]
    )
    assert other_member.status_code == 403

    author = client.delete(f"/api/v1/comments/{comment['id']}", headers=setup["member"]["headers"])
    assert author.status_code == 204

    # Project owner can moderate any comment.
    comment2 = client.post(
        url, json={"body": "owner will remove this"}, headers=setup["second"]["headers"]
    ).json()
    assert (
        client.delete(
            f"/api/v1/comments/{comment2['id']}", headers=setup["owner"]["headers"]
        ).status_code
        == 204
    )
    assert client.get(url, headers=setup["owner"]["headers"]).json() == []
