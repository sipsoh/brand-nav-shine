def test_create_and_list_workspaces(as_user):
    client = as_user(auth_user_id="user_a", email="a@example.com", name="Alice")
    client.post("/users/sync")

    created = client.post("/workspaces", json={"name": "Client Reports"})
    assert created.status_code == 201
    assert created.json()["role"] == "owner"

    listed = client.get("/workspaces").json()["workspaces"]
    names = {w["name"] for w in listed}
    assert names == {"Alice's Workspace", "Client Reports"}


def test_workspace_isolation_between_users(as_user):
    alice = as_user(auth_user_id="user_a", email="a@example.com", name="Alice")
    alice.post("/users/sync")
    alice_workspace_id = alice.get("/workspaces").json()["workspaces"][0]["id"]
    assert alice.get(f"/workspaces/{alice_workspace_id}").status_code == 200

    bob = as_user(auth_user_id="user_b", email="b@example.com", name="Bob")
    bob.post("/users/sync")

    # Bob holds a valid workspace ID but no membership: must read as 404, not 403,
    # so workspace IDs are not enumerable.
    assert bob.get(f"/workspaces/{alice_workspace_id}").status_code == 404

    bob_list = bob.get("/workspaces").json()["workspaces"]
    assert alice_workspace_id not in {w["id"] for w in bob_list}


def test_workspace_endpoints_require_synced_user(as_user):
    client = as_user(auth_user_id="user_never_synced")
    response = client.get("/workspaces")
    assert response.status_code == 401
    assert "sync" in response.json()["detail"].lower()
