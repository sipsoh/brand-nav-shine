"""End-to-end API flow: upload -> dataset creation -> parse job -> profile read."""

import uuid
from pathlib import Path

import pytest

from app.main import app
from app.routers.datasets import get_parse_dispatcher
from app.services.dataset_pipeline import run_parse_dataset
from app.services.storage import ObjectStat, get_storage
from tests.conftest import TestingSession

SAMPLE_CSV = (
    Path(__file__).resolve().parents[3] / "packages" / "sample-data" / "marketing_campaigns.csv"
).read_bytes()


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def presign_put(self, object_key: str, content_type: str | None) -> str:
        return f"https://storage.local/{object_key}"

    def presign_get(self, object_key: str) -> str:
        return f"https://storage.local/{object_key}"

    def stat_object(self, object_key: str) -> ObjectStat | None:
        if object_key not in self.objects:
            return None
        return ObjectStat(size_bytes=len(self.objects[object_key]))

    def get_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]

    def put_bytes(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        self.objects[object_key] = data


@pytest.fixture
def harness(as_user):
    storage = FakeStorage()
    dispatched: list[tuple[uuid.UUID, uuid.UUID]] = []
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_parse_dispatcher] = lambda: (
        lambda dataset_id, job_id: dispatched.append((dataset_id, job_id))
    )
    client = as_user(auth_user_id="user_e2e", email="e2e@example.com", name="E2E")
    workspace_id = client.post("/users/sync").json()["workspaces"][0]["id"]
    return client, storage, dispatched, workspace_id


def upload_file(client, storage, workspace_id) -> str:
    presigned = client.post(
        "/uploads/presign",
        json={
            "workspaceId": workspace_id,
            "filename": "marketing_campaigns.csv",
            "mimeType": "text/csv",
            "sizeBytes": len(SAMPLE_CSV),
        },
    ).json()
    storage.objects[presigned["objectKey"]] = SAMPLE_CSV  # simulate browser PUT
    completed = client.post(f"/uploads/{presigned['fileId']}/complete")
    assert completed.json()["status"] == "uploaded"
    return presigned["fileId"]


def run_dispatched_jobs(storage, dispatched) -> None:
    session = TestingSession()
    try:
        for dataset_id, job_id in dispatched:
            run_parse_dataset(session, storage, dataset_id, job_id)
    finally:
        session.close()


def test_full_flow_upload_to_profile(harness):
    client, storage, dispatched, workspace_id = harness
    file_id = upload_file(client, storage, workspace_id)

    created = client.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": file_id, "name": "June Campaigns"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "queued"
    assert len(dispatched) == 1

    job = client.get(f"/jobs/{body['jobId']}").json()
    assert job["status"] == "queued"

    run_dispatched_jobs(storage, dispatched)

    job = client.get(f"/jobs/{body['jobId']}").json()
    assert job["status"] == "succeeded"
    assert job["progress"] == 100
    assert job["output"]["datasetId"] == body["datasetId"]

    dataset = client.get(f"/datasets/{body['datasetId']}").json()
    assert dataset["name"] == "June Campaigns"
    assert dataset["rowCount"] == 16
    assert dataset["qualityScore"] == 1.0
    assert len(dataset["tables"]) == 1
    table = dataset["tables"][0]
    assert table["columnCount"] == 8
    types = {c["name"]: c["detectedType"] for c in table["columns"]}
    assert types["campaign"] == "category"
    assert types["date"] in {"date", "datetime"}
    assert len(table["sampleRows"]) == 5


def test_from_file_rejects_pending_upload(harness):
    client, storage, dispatched, workspace_id = harness
    presigned = client.post(
        "/uploads/presign",
        json={
            "workspaceId": workspace_id,
            "filename": "x.csv",
            "mimeType": "text/csv",
            "sizeBytes": 10,
        },
    ).json()
    # No PUT, no complete -> still pending.
    response = client.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": presigned["fileId"], "name": "X"},
    )
    assert response.status_code == 409


def test_from_file_requires_membership(harness, as_user):
    client, storage, dispatched, workspace_id = harness
    file_id = upload_file(client, storage, workspace_id)

    intruder = as_user(auth_user_id="user_intruder", email="i@example.com")
    intruder.post("/users/sync")
    response = intruder.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": file_id, "name": "Steal"},
    )
    assert response.status_code == 404


def test_dataset_and_job_reads_are_isolated(harness, as_user):
    client, storage, dispatched, workspace_id = harness
    file_id = upload_file(client, storage, workspace_id)
    body = client.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": file_id, "name": "Private"},
    ).json()
    run_dispatched_jobs(storage, dispatched)

    intruder = as_user(auth_user_id="user_intruder", email="i@example.com")
    intruder.post("/users/sync")
    assert intruder.get(f"/datasets/{body['datasetId']}").status_code == 404
    assert intruder.get(f"/jobs/{body['jobId']}").status_code == 404
