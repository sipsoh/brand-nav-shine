"""The feedback loop: a user's correction on a real dataset becomes a
promotable fixture candidate with the source bytes and a plain-English
account of what was wrong."""

import uuid

import pytest

from app.main import app
from app.routers.datasets import get_parse_dispatcher
from app.services.dataset_pipeline import run_parse_dataset
from app.services.fixture_promotion import PromotionError, build_fixture_candidate
from app.services.storage import get_storage
from tests.conftest import TestingSession

MESSY_CSV = b"""campaign,spend,close_date
Spring Sale,$1250.00,2026-05-04
Brand Push,$980.50,2026-05-11
Retargeting,$640.00,2026-05-25
"""


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def presign_put(self, object_key, content_type=None):
        return f"https://storage.local/{object_key}"

    def presign_get(self, object_key):
        return f"https://storage.local/{object_key}"

    def stat_object(self, object_key):
        from app.services.storage import ObjectStat

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
    client = as_user(auth_user_id="user_promote", email="promote@example.com", name="Promote")
    workspace_id = client.post("/users/sync").json()["workspaces"][0]["id"]
    return client, storage, dispatched, workspace_id


def create_and_parse_dataset(client, storage, dispatched, workspace_id, data: bytes, filename: str):
    presigned = client.post(
        "/uploads/presign",
        json={
            "workspaceId": workspace_id,
            "filename": filename,
            "mimeType": "text/csv",
            "sizeBytes": len(data),
        },
    ).json()
    storage.objects[presigned["objectKey"]] = data
    client.post(f"/uploads/{presigned['fileId']}/complete")

    created = client.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": presigned["fileId"], "name": "Test Dataset"},
    ).json()

    session = TestingSession()
    try:
        for dataset_id, job_id in dispatched:
            run_parse_dataset(session, storage, dataset_id, job_id)
    finally:
        session.close()
    return created["datasetId"]


def test_no_corrections_raises_promotion_error(harness):
    client, storage, dispatched, workspace_id = harness
    dataset_id = create_and_parse_dataset(client, storage, dispatched, workspace_id, MESSY_CSV, "campaigns.csv")

    session = TestingSession()
    try:
        with pytest.raises(PromotionError, match="No user corrections"):
            build_fixture_candidate(session, storage, uuid.UUID(dataset_id))
    finally:
        session.close()


def test_rejected_assumption_becomes_a_correction(harness):
    client, storage, dispatched, workspace_id = harness
    dataset_id = create_and_parse_dataset(client, storage, dispatched, workspace_id, MESSY_CSV, "campaigns.csv")

    dataset = client.get(f"/datasets/{dataset_id}").json()
    assumption = dataset["assumptions"][0]
    patched = client.patch(
        f"/datasets/{dataset_id}/assumptions/{assumption['id']}",
        json={"status": "rejected"},
    )
    assert patched.status_code == 200

    session = TestingSession()
    try:
        candidate = build_fixture_candidate(session, storage, uuid.UUID(dataset_id))
    finally:
        session.close()

    assert candidate.dataset_name == "Test Dataset"
    assert candidate.suggested_slug == "test_dataset"
    assert len(candidate.files) == 1
    assert candidate.files[0][0] == "campaigns.csv"
    assert candidate.files[0][1] == MESSY_CSV
    assert len(candidate.corrections) == 1
    assert candidate.corrections[0].kind == "rejected"
    assert assumption["label"] in candidate.corrections[0].description


def test_semantic_type_correction_captured_with_column_name(harness):
    client, storage, dispatched, workspace_id = harness
    dataset_id = create_and_parse_dataset(client, storage, dispatched, workspace_id, MESSY_CSV, "campaigns.csv")

    dataset = client.get(f"/datasets/{dataset_id}").json()
    assumption = dataset["assumptions"][0]
    patched = client.patch(
        f"/datasets/{dataset_id}/assumptions/{assumption['id']}",
        json={"replacement": {"column": "spend", "semanticType": "cost"}},
    )
    assert patched.status_code == 200

    session = TestingSession()
    try:
        candidate = build_fixture_candidate(session, storage, uuid.UUID(dataset_id))
    finally:
        session.close()

    assert len(candidate.corrections) == 1
    correction = candidate.corrections[0]
    assert correction.kind == "semantic_type_fixed"
    assert "spend" in correction.description
    assert "cost" in correction.description
    # The scaffold should flag the corrected column as forbidden-to-sum by
    # default so the engineer has a concrete assertion to start from.
    forbidden_columns = [f[0] for f in candidate.suggested_expectation["chart_aggregations_forbidden"]]
    assert "spend" in forbidden_columns


def test_missing_dataset_raises(harness):
    _, storage, _, _ = harness
    session = TestingSession()
    try:
        with pytest.raises(PromotionError, match="No dataset"):
            build_fixture_candidate(session, storage, uuid.uuid4())
    finally:
        session.close()
