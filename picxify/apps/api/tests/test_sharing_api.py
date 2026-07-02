"""Publish/unpublish and the public share route."""

from tests.test_dashboards_api import generate, parsed_dataset
from tests.test_datasets_api import harness  # noqa: F401


def published_dashboard(harness, visibility="unlisted"):
    client, storage, workspace_id, dataset_id = parsed_dataset(harness)
    _, body = generate(client, storage, workspace_id, dataset_id, titleHint="Share Me")
    response = client.post(
        f"/dashboards/{body['dashboardId']}/publish", json={"visibility": visibility}
    )
    return client, body["dashboardId"], response


def test_publish_returns_unguessable_share_url(harness):
    client, dashboard_id, response = published_dashboard(harness)
    assert response.status_code == 200
    body = response.json()
    assert body["visibility"] == "unlisted"
    assert body["shareSlug"].startswith("pxf_")
    assert len(body["shareSlug"]) >= 16
    assert body["shareUrl"].endswith(f"/share/{body['shareSlug']}")


def test_share_route_is_public_and_read_only(harness):
    client, dashboard_id, response = published_dashboard(harness)
    slug = response.json()["shareSlug"]

    # No Authorization header involved: the route has no auth dependency.
    share = client.get(f"/shares/{slug}")
    assert share.status_code == 200
    body = share.json()
    assert body["title"] == "Share Me"
    assert body["spec"]["version"] == "0.1.0"
    assert body["spec"]["sections"]


def test_unpublish_makes_share_404_and_republish_reuses_slug(harness):
    client, dashboard_id, response = published_dashboard(harness)
    slug = response.json()["shareSlug"]

    unpublished = client.post(
        f"/dashboards/{dashboard_id}/publish", json={"visibility": "private"}
    )
    assert unpublished.json()["shareUrl"] is None
    assert client.get(f"/shares/{slug}").status_code == 404

    republished = client.post(
        f"/dashboards/{dashboard_id}/publish", json={"visibility": "unlisted"}
    )
    assert republished.json()["shareSlug"] == slug  # existing links keep working
    assert client.get(f"/shares/{slug}").status_code == 200


def test_unknown_slug_is_404(harness):
    client, _, _ = published_dashboard(harness)
    assert client.get("/shares/pxf_does_not_exist").status_code == 404


def test_publish_requires_membership(harness, as_user):
    client, dashboard_id, _ = published_dashboard(harness)
    intruder = as_user(auth_user_id="user_intruder", email="i@example.com")
    intruder.post("/users/sync")
    response = intruder.post(
        f"/dashboards/{dashboard_id}/publish", json={"visibility": "public"}
    )
    assert response.status_code == 404


def test_publish_rejects_bad_visibility(harness):
    client, dashboard_id, _ = published_dashboard(harness)
    response = client.post(
        f"/dashboards/{dashboard_id}/publish", json={"visibility": "everyone"}
    )
    assert response.status_code == 400
