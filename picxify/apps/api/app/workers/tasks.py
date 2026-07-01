"""Celery tasks.

Milestone 1 ships only a ping task to prove the worker connects to Redis.
Parsing, generation, export, and refresh jobs arrive in Milestones 4-9.
"""

from app.config import SERVICE_NAME, SERVICE_VERSION
from app.workers.celery_app import celery_app


@celery_app.task(name="picxify.ping")
def ping() -> dict:
    return {"ok": True, "service": SERVICE_NAME, "version": SERVICE_VERSION}
