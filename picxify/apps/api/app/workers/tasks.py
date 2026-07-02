"""Celery tasks.

Tasks stay thin: they open a session, resolve real services, and delegate to
functions in app.services so the logic is testable without a broker.
"""

import uuid

from app.config import SERVICE_NAME, SERVICE_VERSION
from app.workers.celery_app import celery_app


@celery_app.task(name="picxify.ping")
def ping() -> dict:
    return {"ok": True, "service": SERVICE_NAME, "version": SERVICE_VERSION}


@celery_app.task(name="picxify.parse_dataset")
def parse_dataset_job(dataset_id: str, job_id: str) -> None:
    from app.db import SessionLocal
    from app.services.dataset_pipeline import run_parse_dataset
    from app.services.storage import get_storage

    db = SessionLocal()
    try:
        run_parse_dataset(db, get_storage(), uuid.UUID(dataset_id), uuid.UUID(job_id))
    finally:
        db.close()


@celery_app.task(name="picxify.generate_dashboard")
def generate_dashboard_job(dashboard_id: str, job_id: str) -> None:
    from app.db import SessionLocal
    from app.services.dashboard_pipeline import run_generate_dashboard
    from app.services.storage import get_storage

    db = SessionLocal()
    try:
        run_generate_dashboard(db, get_storage(), uuid.UUID(dashboard_id), uuid.UUID(job_id))
    finally:
        db.close()
