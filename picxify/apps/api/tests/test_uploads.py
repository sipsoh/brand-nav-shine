import uuid

import pytest

from app.main import app
from app.services.storage import ObjectStat, get_storage


class FakeStorage:
    """In-memory stand-in for MinIO/S3."""

    def __init__(self) -> None:
        self.objects: dict[str, int] = {}
        self.presigned: list[str] = []

    def presign_put(self, object_key: str, content_type: str | None) -> str:
        self.presigned.append(object_key)
        return f"https://storage.local/{object_key}?signature=test"

    def presign_get(self, object_key: str) -> str:
        return f"https://storage.local/{object_key}?signature=get"

    def stat_object(self, object_key: str) -> ObjectStat | None:
        if object_key not in self.objects:
            return None
        return ObjectStat(size_bytes=self.objects[object_key])


@pytest.fixture
def storage() -> FakeStorage:
    fake = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    return fake


def _setup_workspace(as_user, **principal_kwargs):
    client = as_user(**principal_kwargs)
    sync = client.post("/users/sync").json()
    return client, sync["workspaces"][0]["id"]


def _presign(client, workspace_id, **overrides):
    body = {
        "workspaceId": workspace_id,
        "filename": "campaigns.csv",
        "mimeType": "text/csv",
        "sizeBytes": 1024,
    }
    body.update(overrides)
    return client.post("/uploads/presign", json=body)


def test_presign_returns_url_and_creates_record(as_user, storage):
    client, workspace_id = _setup_workspace(as_user)
    response = _presign(client, workspace_id)
    assert response.status_code == 200
    body = response.json()
    assert body["uploadUrl"].startswith("https://storage.local/")
    assert body["objectKey"] == f"workspaces/{workspace_id}/uploads/{body['fileId']}/campaigns.csv"
    assert body["expiresInSeconds"] == 900
    assert storage.presigned == [body["objectKey"]]


def test_presign_rejects_unsupported_and_macro_files(as_user, storage):
    client, workspace_id = _setup_workspace(as_user)
    for filename in ["report.pdf", "macro.xlsm", "tool.exe"]:
        response = _presign(client, workspace_id, filename=filename)
        assert response.status_code == 415, filename


def test_presign_rejects_oversized_file(as_user, storage):
    client, workspace_id = _setup_workspace(as_user)
    response = _presign(client, workspace_id, sizeBytes=11 * 1024 * 1024)
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


def test_presign_sanitizes_path_traversal_filenames(as_user, storage):
    client, workspace_id = _setup_workspace(as_user)
    response = _presign(client, workspace_id, filename="../../etc/passwd.csv")
    assert response.status_code == 200
    object_key = response.json()["objectKey"]
    assert ".." not in object_key
    assert object_key.endswith("/passwd.csv")


def test_presign_requires_membership(as_user, storage):
    _, alice_workspace_id = _setup_workspace(
        as_user, auth_user_id="user_a", email="a@example.com"
    )
    bob, _ = _setup_workspace(as_user, auth_user_id="user_b", email="b@example.com")
    response = _presign(bob, alice_workspace_id)
    assert response.status_code == 404


def test_complete_marks_file_uploaded(as_user, storage):
    client, workspace_id = _setup_workspace(as_user)
    presigned = _presign(client, workspace_id).json()
    storage.objects[presigned["objectKey"]] = 2048  # simulate the client PUT

    response = client.post(f"/uploads/{presigned['fileId']}/complete")
    assert response.status_code == 200
    assert response.json() == {"fileId": presigned["fileId"], "status": "uploaded"}

    # Idempotent on retry.
    again = client.post(f"/uploads/{presigned['fileId']}/complete")
    assert again.status_code == 200
    assert again.json()["status"] == "uploaded"


def test_complete_fails_when_object_missing(as_user, storage):
    client, workspace_id = _setup_workspace(as_user)
    presigned = _presign(client, workspace_id).json()
    response = client.post(f"/uploads/{presigned['fileId']}/complete")
    assert response.status_code == 409
    assert "retry" in response.json()["detail"].lower()


def test_complete_rejects_lied_about_size(as_user, storage):
    client, workspace_id = _setup_workspace(as_user)
    presigned = _presign(client, workspace_id, sizeBytes=1024).json()
    storage.objects[presigned["objectKey"]] = 50 * 1024 * 1024  # actual object is 50 MB

    response = client.post(f"/uploads/{presigned['fileId']}/complete")
    assert response.status_code == 413


def test_complete_requires_membership(as_user, storage):
    alice, workspace_id = _setup_workspace(
        as_user, auth_user_id="user_a", email="a@example.com"
    )
    presigned = _presign(alice, workspace_id).json()
    storage.objects[presigned["objectKey"]] = 1024

    bob, _ = _setup_workspace(as_user, auth_user_id="user_b", email="b@example.com")
    response = bob.post(f"/uploads/{presigned['fileId']}/complete")
    assert response.status_code == 404


def test_complete_unknown_file_is_404(as_user, storage):
    client, _ = _setup_workspace(as_user)
    response = client.post(f"/uploads/{uuid.uuid4()}/complete")
    assert response.status_code == 404
