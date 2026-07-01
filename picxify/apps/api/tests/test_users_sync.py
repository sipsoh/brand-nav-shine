def test_sync_creates_user_and_default_workspace(as_user):
    client = as_user(auth_user_id="user_new", email="new@example.com", name="New User")
    response = client.post("/users/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["user"]["email"] == "new@example.com"
    assert len(body["workspaces"]) == 1
    workspace = body["workspaces"][0]
    assert workspace["name"] == "New User's Workspace"
    assert workspace["role"] == "owner"
    assert workspace["slug"]


def test_sync_is_idempotent(as_user):
    client = as_user(auth_user_id="user_repeat", email="repeat@example.com")
    first = client.post("/users/sync").json()
    second = client.post("/users/sync").json()
    assert second["created"] is False
    assert second["user"]["id"] == first["user"]["id"]
    assert len(second["workspaces"]) == 1
    assert second["workspaces"][0]["id"] == first["workspaces"][0]["id"]


def test_sync_updates_changed_profile(as_user):
    as_user(auth_user_id="user_x", email="old@example.com", name="Old Name").post("/users/sync")
    body = (
        as_user(auth_user_id="user_x", email="new@example.com", name="New Name")
        .post("/users/sync")
        .json()
    )
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["name"] == "New Name"


def test_sync_requires_auth(client):
    response = client.post("/users/sync")
    assert response.status_code == 401
