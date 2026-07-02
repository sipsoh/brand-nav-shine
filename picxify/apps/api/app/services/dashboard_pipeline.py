"""The generate_dashboard job (SETUP.md §9 steps G-N, §22).

Deterministic orchestration: load profiled data -> compute facts (code) ->
select template -> plan spec (LLM or fallback) -> execute charts (code) ->
validate spec + source traces -> persist a new dashboard version.
"""

import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.assumption import Assumption
from app.models.dashboard import Dashboard, DashboardVersion
from app.models.dataset import DataQualityFinding, Dataset, DatasetTable
from app.models.job import GenerationJob, JobStatus
from app.prompts.dashboard_planner_prompt import PROMPT_VERSION
from app.services.dashboard_planner import (
    ColumnCtx,
    PlanningContext,
    execute_charts,
    plan_dashboard,
)
from app.services.insight_engine import ColumnMeta, compute_insights, quality_insights
from app.services.llm import get_planner_llm
from app.services.spec_validator import (
    SpecValidationError,
    assert_source_traces,
    validate_spec,
)
from app.services.templates import select_template

logger = logging.getLogger(__name__)

STEPS = [
    (15, "Selecting template"),
    (40, "Computing facts"),
    (65, "Planning dashboard"),
    (80, "Building charts"),
    (95, "Validating sources"),
]


class GenerationError(Exception):
    pass


def run_generate_dashboard(
    db: Session, storage, dashboard_id: uuid.UUID, job_id: uuid.UUID
) -> None:
    job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
    dashboard = db.scalar(select(Dashboard).where(Dashboard.id == dashboard_id))
    if job is None or dashboard is None:
        logger.error("generate_dashboard: missing job %s or dashboard %s", job_id, dashboard_id)
        return
    try:
        _run(db, storage, dashboard, job)
    except GenerationError as error:
        _fail(db, job, str(error))
    except Exception:
        logger.exception("generate_dashboard failed (job=%s)", job_id)
        _fail(db, job, "Something went wrong while generating this dashboard. Please try again.")


def _run(db: Session, storage, dashboard: Dashboard, job: GenerationJob) -> None:
    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.now(timezone.utc)
    _progress(db, job, *STEPS[0])

    dataset = db.scalar(
        select(Dataset)
        .where(Dataset.id == dashboard.dataset_id)
        .options(selectinload(Dataset.tables).selectinload(DatasetTable.columns))
    )
    if dataset is None or not dataset.tables:
        raise GenerationError("This dataset has not been parsed yet.")

    tables_with_snapshots = [t for t in dataset.tables if t.snapshot_object_key]
    if not tables_with_snapshots:
        raise GenerationError("No processed data snapshot found for this dataset.")
    primary = max(tables_with_snapshots, key=lambda t: t.row_count)
    df = pd.read_parquet(BytesIO(storage.get_bytes(primary.snapshot_object_key)))
    frames = {str(primary.id): df}

    options = job.input or {}
    use_case = options.get("useCaseHint") or (
        (dataset.profile.get("useCaseCandidates") or [{}])[0].get("useCase") or "generic"
    )
    audience = options.get("audience") or "client"
    template = select_template(use_case)
    dashboard.template_code = template["code"]

    _progress(db, job, *STEPS[1])
    columns_meta = [
        ColumnMeta(
            name=c.name,
            detected_type=c.detected_type,
            semantic_type=c.semantic_type,
            role_hint=c.role_hint,
        )
        for c in primary.columns
    ]
    result = compute_insights(df, table_id=str(primary.id), columns=columns_meta)
    findings = db.scalars(
        select(DataQualityFinding).where(DataQualityFinding.table_id == primary.id)
    ).all()
    result.insights.extend(quality_insights(findings, table_id=str(primary.id)))

    assumptions = db.scalars(
        select(Assumption).where(Assumption.dataset_id == dataset.id).order_by(Assumption.created_at)
    ).all()

    _progress(db, job, *STEPS[2])
    ctx = PlanningContext(
        dataset_id=str(dataset.id),
        dataset_name=dataset.name,
        table_id=str(primary.id),
        table_name=primary.name,
        row_count=primary.row_count,
        column_count=primary.column_count,
        snapshot_uri=primary.snapshot_object_key,
        columns=[
            ColumnCtx(
                name=c.name,
                detected_type=c.detected_type,
                semantic_type=c.semantic_type,
                role_hint=c.role_hint,
            )
            for c in primary.columns
        ],
        facts=[fact.to_dict() for fact in result.facts],
        insights=[insight.to_dict() for insight in result.insights],
        assumptions=[
            {
                "id": str(a.id),
                "label": a.label[:200],
                "status": a.status,
                "confidence": float(a.confidence) if a.confidence is not None else 0.5,
                "editable": a.editable,
                "source": a.source,
                "affectedColumns": list(a.affected_columns or []),
            }
            for a in assumptions
        ],
        use_case=use_case,
        audience=audience,
        template=template,
        date_grain=_pick_date_grain(df, primary.columns),
        title_hint=options.get("titleHint"),
    )
    spec, planner = plan_dashboard(ctx, llm=get_planner_llm())

    _progress(db, job, *STEPS[3])
    execute_charts(spec, frames)

    _progress(db, job, *STEPS[4])
    try:
        validate_spec(spec)
        assert_source_traces(spec)
    except SpecValidationError as error:
        raise GenerationError(f"Generated dashboard failed validation: {error}") from error

    next_number = (
        db.scalar(
            select(func.max(DashboardVersion.version_number)).where(
                DashboardVersion.dashboard_id == dashboard.id
            )
        )
        or 0
    ) + 1
    version = DashboardVersion(
        dashboard_id=dashboard.id,
        version_number=next_number,
        spec=spec,
        generation_metadata={
            "planner": planner,
            "promptVersion": PROMPT_VERSION,
            "templateCode": template["code"],
            "jobId": str(job.id),
        },
        created_by=job.user_id,
    )
    db.add(version)
    db.flush()

    dashboard.current_version_id = version.id
    dashboard.title = spec["dashboard"]["title"][:200]
    dashboard.subtitle = spec["dashboard"]["subtitle"][:500]

    job.status = JobStatus.SUCCEEDED.value
    job.progress = 100
    job.current_step = "Done"
    job.dashboard_id = dashboard.id
    job.output = {
        "dashboardId": str(dashboard.id),
        "versionId": str(version.id),
        "versionNumber": next_number,
    }
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def _pick_date_grain(df: pd.DataFrame, columns) -> str | None:
    date_column = next((c.name for c in columns if c.role_hint == "date"), None)
    if date_column is None or not pd.api.types.is_datetime64_any_dtype(df[date_column]):
        return None
    series = df[date_column].dropna()
    if series.empty:
        return None
    span_days = (series.max() - series.min()).days
    return "month" if span_days >= 70 else "week"


def _progress(db: Session, job: GenerationJob, progress: int, step: str) -> None:
    job.progress = progress
    job.current_step = step
    db.commit()


def _fail(db: Session, job: GenerationJob, message: str) -> None:
    db.rollback()
    job.status = JobStatus.FAILED.value
    job.error_message = message
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
