"""Assumption review flow on top of the full upload -> parse pipeline."""

from tests.test_datasets_api import harness, run_dispatched_jobs, upload_file  # noqa: F401


def parsed_dataset(harness):
    client, storage, dispatched, workspace_id = harness
    file_id = upload_file(client, storage, workspace_id)
    body = client.post(
        "/datasets/from-file",
        json={"workspaceId": workspace_id, "fileId": file_id, "name": "Campaigns"},
    ).json()
    run_dispatched_jobs(storage, dispatched)
    return client, body["datasetId"]


def test_pipeline_produces_semantic_types_and_assumptions(harness):
    client, dataset_id = parsed_dataset(harness)
    dataset = client.get(f"/datasets/{dataset_id}").json()

    assert dataset["useCaseCandidates"][0]["useCase"] == "marketing"

    semantic_types = {
        c["name"]: c["semanticType"] for c in dataset["tables"][0]["columns"]
    }
    assert semantic_types["spend"] == "cost"
    assert semantic_types["campaign"] == "campaign"
    assert semantic_types["date"] == "date"

    assert len(dataset["assumptions"]) >= 1
    assert all(a["status"] == "needs_review" for a in dataset["assumptions"])


def test_accept_and_reject_assumption(harness):
    client, dataset_id = parsed_dataset(harness)
    assumptions = client.get(f"/datasets/{dataset_id}").json()["assumptions"]

    accepted = client.patch(
        f"/datasets/{dataset_id}/assumptions/{assumptions[0]['id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    rejected = client.patch(
        f"/datasets/{dataset_id}/assumptions/{assumptions[0]['id']}",
        json={"status": "rejected"},
    )
    assert rejected.json()["status"] == "rejected"

    bad = client.patch(
        f"/datasets/{dataset_id}/assumptions/{assumptions[0]['id']}",
        json={"status": "maybe"},
    )
    assert bad.status_code == 400


def test_replacement_remaps_column(harness):
    client, dataset_id = parsed_dataset(harness)
    assumptions = client.get(f"/datasets/{dataset_id}").json()["assumptions"]

    response = client.patch(
        f"/datasets/{dataset_id}/assumptions/{assumptions[0]['id']}",
        json={"replacement": {"column": "revenue", "semanticType": "revenue"}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    dataset = client.get(f"/datasets/{dataset_id}").json()
    semantic_types = {c["name"]: c["semanticType"] for c in dataset["tables"][0]["columns"]}
    assert semantic_types["revenue"] == "revenue"


def test_replacement_with_unknown_column_is_404(harness):
    client, dataset_id = parsed_dataset(harness)
    assumptions = client.get(f"/datasets/{dataset_id}").json()["assumptions"]
    response = client.patch(
        f"/datasets/{dataset_id}/assumptions/{assumptions[0]['id']}",
        json={"replacement": {"column": "ghost", "semanticType": "revenue"}},
    )
    assert response.status_code == 404


def test_assumption_edit_requires_membership(harness, as_user):
    client, dataset_id = parsed_dataset(harness)
    assumptions = client.get(f"/datasets/{dataset_id}").json()["assumptions"]

    intruder = as_user(auth_user_id="user_intruder", email="i@example.com")
    intruder.post("/users/sync")
    response = intruder.patch(
        f"/datasets/{dataset_id}/assumptions/{assumptions[0]['id']}",
        json={"status": "accepted"},
    )
    assert response.status_code == 404
