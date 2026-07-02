"""Promote a customer's corrected dataset into a permanent eval fixture.

When a user rejects an assumption or fixes a column's semantic type, the
engine got something wrong on their file's specific shape. This is the
feedback loop that makes the mistake permanent to fix: it pulls the source
file(s) and a plain-English account of what was corrected, so an engineer can
drop the file(s) into packages/sample-data/complex/, review the scaffolded
eval expectation, and land it — turning one customer's confusion into a
regression test that runs forever.

Usage (from apps/api, venv active, DATABASE_URL pointed at the real DB):
    python -m scripts.promote_fixture <dataset_id>
    python -m scripts.promote_fixture <dataset_id> --out-dir /path/to/fixtures
"""

import argparse
import sys
import uuid
from pathlib import Path

from app.db import SessionLocal
from app.services.fixture_promotion import PromotionError, build_fixture_candidate
from app.services.storage import get_storage

DEFAULT_OUT_DIR = (
    Path(__file__).resolve().parents[3] / "packages" / "sample-data" / "complex"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_id", type=str)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    try:
        dataset_id = uuid.UUID(args.dataset_id)
    except ValueError:
        print(f"'{args.dataset_id}' is not a valid dataset id.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        storage = get_storage()
        candidate = build_fixture_candidate(db, storage, dataset_id)
    except PromotionError as error:
        print(f"Nothing to promote: {error}", file=sys.stderr)
        return 1
    finally:
        db.close()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, data in candidate.files:
        suffix = Path(filename).suffix or ".dat"
        target = args.out_dir / f"{candidate.suggested_slug}{suffix}"
        target.write_bytes(data)
        written.append(target)

    print(f"# Fixture candidate: {candidate.dataset_name!r}\n")
    print("## What the user corrected (why this is worth learning from)")
    for correction in candidate.corrections:
        print(f"  - [{correction.kind}] {correction.description}")

    print("\n## Files written")
    for target in written:
        print(f"  - {target}")

    print("\n## Scaffolded evals/run_evals.py EXPECTATIONS entry — REVIEW before landing:")
    print(f'    "{written[0].name}": {{')
    for key, value in candidate.suggested_expectation.items():
        if key == "filename":
            continue
        print(f"        {key!r}: {value!r},")
    print("    },")
    print(
        "\nThe scaffold reflects CURRENT behavior, which may still be the bug the user "
        "reported. Edit required_kpi_tokens / chart_aggregations_forbidden to assert the "
        "CORRECTED behavior before adding this to EXPECTATIONS."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
