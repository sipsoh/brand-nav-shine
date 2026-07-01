from app.workers.celery_app import celery_app
from app.workers.tasks import ping


def test_celery_app_configured():
    assert celery_app.main == "picxify"
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_ping_task_registered_and_runs_eagerly():
    assert "picxify.ping" in celery_app.tasks
    result = ping.run()
    assert result["ok"] is True
    assert result["service"] == "picxify-api"
