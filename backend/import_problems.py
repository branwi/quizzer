"""Import a JSON question list: python -m backend.import_problems [path]."""

import argparse
from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, create_tables
from backend.models import Question
from backend.schemas import QuestionCreate

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "competition_problems.json"


def import_problems(db: Session, path: Path = DEFAULT_PATH) -> tuple[int, int]:
    # Validate the whole file before adding anything. One commit keeps the batch atomic.
    problems = TypeAdapter(list[QuestionCreate]).validate_json(path.read_text(encoding="utf-8"))
    existing = set(db.scalars(select(Question.text)))
    added = 0
    for problem in problems:
        if problem.text in existing:
            continue
        db.add(Question(**problem.model_dump()))
        existing.add(problem.text)
        added += 1
    db.commit()
    return added, len(problems) - added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    create_tables()
    with SessionLocal() as db:
        added, skipped = import_problems(db, args.path)
    print(f"Imported {added} problems; skipped {skipped} duplicates.")


if __name__ == "__main__":
    main()
