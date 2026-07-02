"""The feedback loop: turn a user's correction into a permanent eval fixture.

When someone rejects an assumption or fixes a column's semantic type, that is
real signal the engine got something wrong on their specific file shape. This
module packages that signal — the source file bytes plus a human-readable
account of what was corrected — so an engineer can drop it straight into
packages/sample-data/complex/ and evals/run_evals.py, turning one customer's
confusion into a permanent regression test. See scripts/promote_fixture.py
for the CLI that drives this.
"""

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assumption import Assumption, AssumptionStatus
from app.models.dataset import Dataset, DatasetTable
from app.services.dataset_pipeline import linked_files


@dataclass
class Correction:
    table: str | None
    kind: str  # "rejected" | "semantic_type_fixed"
    description: str


@dataclass
class FixtureCandidate:
    dataset_name: str
    suggested_slug: str
    files: list[tuple[str, bytes]]  # (original_filename, raw_bytes)
    corrections: list[Correction]
    tables: list[dict]  # name, rowCount, structureConfidence — for the expectation scaffold
    use_case: str | None
    suggested_expectation: dict = field(default_factory=dict)


class PromotionError(Exception):
    """No signal worth promoting, or the dataset/files couldn't be loaded."""


def build_fixture_candidate(db: Session, storage, dataset_id: uuid.UUID) -> FixtureCandidate:
    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))
    if dataset is None:
        raise PromotionError(f"No dataset {dataset_id}.")

    files = linked_files(db, dataset)
    if not files:
        raise PromotionError("This dataset's source file(s) no longer exist.")

    corrections = _collect_corrections(db, dataset_id)
    if not corrections:
        raise PromotionError(
            "No user corrections found on this dataset — nothing to learn from yet."
        )

    file_bytes = [(f.original_filename, storage.get_bytes(f.object_key)) for f in files]

    tables = db.scalars(select(DatasetTable).where(DatasetTable.dataset_id == dataset_id)).all()
    table_summaries = [
        {
            "name": t.name,
            "rowCount": t.row_count,
            "structureConfidence": (t.profile or {}).get("structureConfidence"),
        }
        for t in tables
    ]
    use_case = ((dataset.profile or {}).get("useCaseCandidates") or [{}])[0].get("useCase")

    slug = _slugify(dataset.name)
    return FixtureCandidate(
        dataset_name=dataset.name,
        suggested_slug=slug,
        files=file_bytes,
        corrections=corrections,
        tables=table_summaries,
        use_case=use_case,
        suggested_expectation=_scaffold_expectation(file_bytes, table_summaries, use_case, corrections),
    )


def _collect_corrections(db: Session, dataset_id: uuid.UUID) -> list[Correction]:
    assumptions = db.scalars(
        select(Assumption).where(Assumption.dataset_id == dataset_id)
    ).all()
    corrections: list[Correction] = []
    for assumption in assumptions:
        replacement = (assumption.meta or {}).get("replacement")
        if replacement and (assumption.meta or {}).get("byUser"):
            corrections.append(
                Correction(
                    table=None,
                    kind="semantic_type_fixed",
                    description=(
                        f"User remapped '{replacement.get('column')}' to "
                        f"semantic type '{replacement.get('semanticType')}' "
                        f"(engine had guessed differently: {assumption.label})"
                    ),
                )
            )
        elif assumption.status == AssumptionStatus.REJECTED.value:
            corrections.append(
                Correction(
                    table=None,
                    kind="rejected",
                    description=f"User rejected: {assumption.label}",
                )
            )
    return corrections


def _scaffold_expectation(
    file_bytes: list[tuple[str, bytes]],
    tables: list[dict],
    use_case: str | None,
    corrections: list[Correction],
) -> dict:
    """A best-guess EXPECTATIONS entry for evals/run_evals.py — always meant
    to be reviewed by a human, never auto-committed. It encodes the CURRENT
    (possibly still-wrong) behavior as a starting point; the engineer edits
    it to assert the CORRECTED behavior before landing the fixture."""
    primary = max(tables, key=lambda t: t["rowCount"], default=None)
    forbidden = []
    for correction in corrections:
        match = re.search(r"remapped '([^']+)'", correction.description)
        if match:
            forbidden.append([match.group(1), "sum"])
    return {
        "filename": file_bytes[0][0] if len(file_bytes) == 1 else "<combined-or-joined-name>",
        "use_case": use_case,
        "primary_sheet": primary["name"] if primary else None,
        "required_kpi_tokens": ["rows analyzed"],
        "chart_aggregations_forbidden": [tuple(f) for f in forbidden],
    }


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "customer_fixture"
