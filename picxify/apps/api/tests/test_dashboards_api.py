"""End-to-end: upload -> parse -> generate dashboard -> read validated spec."""

import uuid

from app.main import app
from app.routers.dashboards import get_generate_dispatcher
from app.services.dashboard_pipeline import run_generate_dashboard
from app.services.spec_validator import assert_source_traces, validate_spec
from tests.conftest import TestingSession
from tests.test_datasets_api import harness, run_dispatched_jobs, upload_file  # noqa: F401


def parsed_dataset(harness):
    client, storage, dispatched, workspace_id = harness
    file_id = upload_file(client, storage, workspace_id)
    body = client.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": file_id, "name": "June Campaigns"},
    ).json()
    run_dispatched_jobs(storage, dispatched)
    dispatched.clear()
    return client, storage, workspace_id, body["datasetId"]


def generate(client, storage, workspace_id, dataset_id, **overrides):
    generated: list[tuple[uuid.UUID, uuid.UUID]] = []
    app.dependency_overrides[get_generate_dispatcher] = lambda: (
        lambda dashboard_id, job_id: generated.append((dashboard_id, job_id))
    )
    body = {"workspaceId": workspace_id, "datasetId": dataset_id, "audience": "client"}
    body.update(overrides)
    response = client.post("/dashboards/generate", json=body)
    if response.status_code != 200:
        return response, None
    session = TestingSession()
    try:
        for dashboard_id, job_id in generated:
            run_generate_dashboard(session, storage, dashboard_id, job_id)
    finally:
        session.close()
    return response, response.json()


def test_generate_dashboard_end_to_end(harness):
    client, storage, workspace_id, dataset_id = parsed_dataset(harness)
    response, body = generate(client, storage, workspace_id, dataset_id, titleHint="June Report")
    assert response.status_code == 200

    job = client.get(f"/jobs/{body['jobId']}").json()
    assert job["status"] == "succeeded", job["errorMessage"]
    assert job["output"]["versionNumber"] == 1

    dashboard = client.get(f"/dashboards/{body['dashboardId']}").json()
    assert dashboard["title"] == "June Report"
    version = dashboard["currentVersion"]
    assert version["versionNumber"] == 1
    assert version["generationMetadata"]["planner"] == "fallback"  # keyless env

    spec = version["spec"]
    validate_spec(spec)
    assert_source_traces(spec)
    assert spec["dashboard"]["useCase"] == "marketing"
    assert spec["dashboard"]["audience"] == "client"

    charts = [
        w["chart"]
        for section in spec["sections"]
        for w in section["widgets"]
        if w["type"] == "chart"
    ]
    assert charts
    for chart in charts:
        assert chart["echartsOption"].get("series")

    assert spec["assumptions"], "dataset assumptions should be carried into the spec"


def test_generated_dashboard_appears_in_list(harness):
    client, storage, workspace_id, dataset_id = parsed_dataset(harness)
    _, body = generate(client, storage, workspace_id, dataset_id)
    listed = client.get(f"/dashboards?workspaceId={workspace_id}").json()["dashboards"]
    assert any(d["dashboardId"] == body["dashboardId"] and d["hasVersion"] for d in listed)


def test_generate_rejects_unparsed_dataset(harness):
    client, storage, dispatched, workspace_id = harness
    file_id = upload_file(client, storage, workspace_id)
    body = client.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": file_id, "name": "Unparsed"},
    ).json()
    # Parse job dispatched but never run -> dataset has no row_count yet.
    response = client.post(
        "/dashboards/generate",
        json={"workspaceId": workspace_id, "datasetId": body["datasetId"], "audience": "client"},
    )
    assert response.status_code == 409


def test_dashboard_reads_are_isolated(harness, as_user):
    client, storage, workspace_id, dataset_id = parsed_dataset(harness)
    _, body = generate(client, storage, workspace_id, dataset_id)

    intruder = as_user(auth_user_id="user_intruder", email="i@example.com")
    intruder.post("/users/sync")
    assert intruder.get(f"/dashboards/{body['dashboardId']}").status_code == 404
    assert intruder.get(f"/dashboards?workspaceId={workspace_id}").status_code == 404


def test_generate_rejects_bad_audience(harness):
    client, storage, workspace_id, dataset_id = parsed_dataset(harness)
    response = client.post(
        "/dashboards/generate",
        json={"workspaceId": workspace_id, "datasetId": dataset_id, "audience": "aliens"},
    )
    assert response.status_code == 400
