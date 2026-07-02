"""Smoke test for the scripts/promote_fixture.py CLI: run its real main()
against the test harness (SessionLocal/get_storage monkeypatched) to prove
the argument parsing, file writing, and print formatting actually work end
to end — not just the underlying build_fixture_candidate() logic."""

import uuid

import pytest

import scripts.promote_fixture as cli
from app.main import app
from app.routers.datasets import get_parse_dispatcher
from app.services.dataset_pipeline import run_parse_dataset
from app.services.storage import get_storage
from tests.conftest import TestingSession
from tests.test_fixture_promotion import FakeStorage, MESSY_CSV


@pytest.fixture
def harness(as_user):
    storage = FakeStorage()
    dispatched: list[tuple[uuid.UUID, uuid.UUID]] = []
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_parse_dispatcher] = lambda: (
        lambda dataset_id, job_id: dispatched.append((dataset_id, job_id))
    )
    client = as_user(auth_user_id="user_cli", email="cli@example.com", name="CLI")
    workspace_id = client.post("/users/sync").json()["workspaces"][0]["id"]
    return client, storage, dispatched, workspace_id


def test_cli_writes_fixture_and_prints_scaffold(harness, tmp_path, capsys, monkeypatch):
    client, storage, dispatched, workspace_id = harness
    presigned = client.post(
        "/uploads/presign",
        json={
            "workspaceId": workspace_id,
            "filename": "campaigns.csv",
            "mimeType": "text/csv",
            "sizeBytes": len(MESSY_CSV),
        },
    ).json()
    storage.objects[presigned["objectKey"]] = MESSY_CSV
    client.post(f"/uploads/{presigned['fileId']}/complete")
    created = client.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": presigned["fileId"], "name": "CLI Test Dataset"},
    ).json()

    session = TestingSession()
    try:
        for dataset_id, job_id in dispatched:
            run_parse_dataset(session, storage, dataset_id, job_id)
    finally:
        session.close()

    dataset_id = created["datasetId"]
    dataset = client.get(f"/datasets/{dataset_id}").json()
    assumption = dataset["assumptions"][0]
    client.patch(
        f"/datasets/{dataset_id}/assumptions/{assumption['id']}", json={"status": "rejected"}
    )

    monkeypatch.setattr(cli, "SessionLocal", TestingSession)
    monkeypatch.setattr(cli, "get_storage", lambda: storage)
    monkeypatch.setattr(
        "sys.argv", ["promote_fixture.py", dataset_id, "--out-dir", str(tmp_path)]
    )

    exit_code = cli.main()
    assert exit_code == 0

    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].read_bytes() == MESSY_CSV

    output = capsys.readouterr().out
    assert "CLI Test Dataset" in output
    assert "[rejected]" in output
    assert "EXPECTATIONS entry" in output


def test_cli_reports_error_for_unknown_dataset(capsys, monkeypatch):
    from app.services.storage import get_storage as real_get_storage

    monkeypatch.setattr(cli, "SessionLocal", TestingSession)
    monkeypatch.setattr(cli, "get_storage", real_get_storage)
    monkeypatch.setattr("sys.argv", ["promote_fixture.py", str(uuid.uuid4())])

    exit_code = cli.main()
    assert exit_code == 1
