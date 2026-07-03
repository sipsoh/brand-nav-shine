"""LocalDiskStorageService and its /local-storage PUT/GET routes — the
no-Docker path for local dev (STORAGE_BACKEND=local instead of MinIO/S3)."""

import shutil
import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.main import app
from app.routers.datasets import get_parse_dispatcher
from app.services.dataset_pipeline import run_parse_dataset
from app.services.storage import LocalDiskStorageService, get_storage
from tests.conftest import TestingSession

SAMPLE_CSV = (
    Path(__file__).resolve().parents[3] / "packages" / "sample-data" / "marketing_campaigns.csv"
).read_bytes()


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    service = LocalDiskStorageService()
    yield service
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_put_and_get_bytes_round_trip(local_storage):
    key = f"workspaces/w1/uploads/{uuid.uuid4()}/data.csv"
    local_storage.put_bytes(key, b"a,b\n1,2\n")
    assert local_storage.get_bytes(key) == b"a,b\n1,2\n"


def test_stat_object_missing_returns_none(local_storage):
    assert local_storage.stat_object("workspaces/w1/uploads/does-not-exist.csv") is None


def test_stat_object_reports_size(local_storage):
    key = "workspaces/w1/uploads/x/report.csv"
    local_storage.put_bytes(key, b"hello world")
    stat = local_storage.stat_object(key)
    assert stat is not None
    assert stat.size_bytes == len(b"hello world")


def test_presigned_urls_point_at_the_api_itself(local_storage):
    key = "workspaces/w1/uploads/x/report.csv"
    assert local_storage.presign_put(key, "text/csv") == f"{settings.api_url}/local-storage/{key}"
    assert local_storage.presign_get(key) == f"{settings.api_url}/local-storage/{key}"


def test_path_traversal_key_rejected(local_storage):
    with pytest.raises(ValueError):
        local_storage.put_bytes("../../etc/passwd", b"nope")


def test_local_storage_routes_disabled_unless_backend_is_local(client, monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "s3")
    response = client.get("/local-storage/anything")
    assert response.status_code == 404
    response = client.put("/local-storage/anything", content=b"x")
    assert response.status_code == 404


def test_local_storage_routes_serve_bytes_when_enabled(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    app.dependency_overrides[get_storage] = lambda: LocalDiskStorageService()
    try:
        key = f"workspaces/w1/uploads/{uuid.uuid4()}/report.csv"
        put_response = client.put(f"/local-storage/{key}", content=b"a,b\n1,2\n")
        assert put_response.status_code == 200

        get_response = client.get(f"/local-storage/{key}")
        assert get_response.status_code == 200
        assert get_response.content == b"a,b\n1,2\n"

        missing = client.get("/local-storage/workspaces/w1/uploads/does-not-exist.csv")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.pop(get_storage, None)


def test_full_upload_to_dashboard_flow_over_local_storage(as_user, tmp_path, monkeypatch):
    """The exact path a user's browser takes — presign, PUT the file bytes,
    complete, parse — but landing on local disk instead of MinIO/S3. Proves
    the no-Docker dev path works end to end, not just its parts in isolation."""
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    app.dependency_overrides[get_storage] = lambda: LocalDiskStorageService()
    dispatched: list[tuple] = []
    app.dependency_overrides[get_parse_dispatcher] = lambda: (
        lambda dataset_id, job_id: dispatched.append((dataset_id, job_id))
    )
    try:
        client = as_user(auth_user_id="user_local", email="local@example.com", name="Local")
        workspace_id = client.post("/users/sync").json()["workspaces"][0]["id"]

        presigned = client.post(
            "/uploads/presign",
            json={
                "workspaceId": workspace_id,
                "filename": "marketing_campaigns.csv",
                "mimeType": "text/csv",
                "sizeBytes": len(SAMPLE_CSV),
            },
        ).json()
        assert presigned["uploadUrl"] == f"{settings.api_url}/local-storage/{presigned['objectKey']}"

        # The real browser flow: PUT straight to the returned URL.
        put_response = client.put(presigned["uploadUrl"], content=SAMPLE_CSV)
        assert put_response.status_code == 200

        completed = client.post(f"/uploads/{presigned['fileId']}/complete").json()
        assert completed["status"] == "uploaded"

        created = client.post(
            "/datasets/from-file",
            json={
                "workspaceId": workspace_id,
                "fileId": presigned["fileId"],
                "name": "Local Storage Test",
            },
        ).json()

        session = TestingSession()
        try:
            for dataset_id, job_id in dispatched:
                run_parse_dataset(session, LocalDiskStorageService(), dataset_id, job_id)
        finally:
            session.close()

        job = client.get(f"/jobs/{created['jobId']}").json()
        assert job["status"] == "succeeded"
        dataset = client.get(f"/datasets/{created['datasetId']}").json()
        assert dataset["rowCount"] == 16
    finally:
        app.dependency_overrides.pop(get_storage, None)
        app.dependency_overrides.pop(get_parse_dispatcher, None)
