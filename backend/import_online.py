"""Fetch competition problems from MathNet's public Hugging Face API."""

import argparse
import io
import json
import re
import time
from collections.abc import Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, create_tables
from backend.models import Question
from backend.schemas import QuestionCreate

DATASET_URL = "https://huggingface.co/datasets/ShadenA/MathNet"
FILES_API = "https://huggingface.co/api/datasets/ShadenA/MathNet/tree/main/data/all?limit=1000"
TEXT_COLUMNS = [
    "id",
    "problem_markdown",
    "solutions_markdown",
    "country",
    "competition",
    "topics_flat",
    "language",
    "problem_type",
    "final_answer",
]
IMAGE_REFERENCE = re.compile(
    r"!\[|<img|\\includegraphics|attached_image|\b(?:diagram|figure)\s+(?:below|above)", re.I
)
SOURCE_ID = re.compile(r"MathNet #([A-Za-z0-9_-]+)")


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ProblemRoom/1.0"})
    for attempt in range(4):
        delay = 2 ** (attempt + 1)
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            if exc.code == 429:
                # Respect the provider's requested delay; do not retry in a tight loop.
                retry_after = exc.headers.get("Retry-After", "60")
                delay = max(delay, int(retry_after)) if retry_after.isdigit() else 60
        except (URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(delay)
    raise RuntimeError("Could not fetch MathNet problems")


def fetch_batches() -> Iterator[list[dict]]:
    # Bulk files avoid hundreds of calls to the rate-limited dataset preview API.
    import pyarrow.parquet as parquet

    files = json.loads(download(FILES_API))
    paths = sorted(
        entry["path"]
        for entry in files
        if entry.get("type") == "file"
        and entry["path"].endswith(".parquet")
        and entry["path"].startswith("data/all/")
    )
    if not paths:
        raise ValueError("MathNet did not return any dataset files")
    for path in paths:
        url = f"{DATASET_URL}/resolve/main/{quote(path, safe='/')}"
        with io.BytesIO(download(url)) as data:
            # Images are deliberately not decoded or stored in this app.
            yield parquet.ParquetFile(data).read(columns=TEXT_COLUMNS).to_pylist()


def convert(row: dict) -> QuestionCreate | None:
    """Only use English questions with a single integer answer and no required images."""
    if row.get("language") != "English" or row.get("problem_type") == "proof only":
        return None
    answer = str(row.get("final_answer") or "").strip().strip("$").strip()
    text = row.get("problem_markdown")
    source_id = str(row.get("id") or "")
    if (
        not re.fullmatch(r"[+-]?[0-9]{1,100}", answer)
        or not isinstance(text, str)
        or not text.strip()
        or IMAGE_REFERENCE.search(text)
        or not re.fullmatch(r"[A-Za-z0-9_-]+", source_id)
    ):
        return None
    answer = str(int(answer))
    solutions = row.get("solutions_markdown") or []
    explanation = next(
        (
            s
            for s in solutions
            if isinstance(s, str) and s.strip() and not IMAGE_REFERENCE.search(s) and len(s) <= 8500
        ),
        "A worked solution is available in the source dataset.",
    )
    topics = row.get("topics_flat") or []
    topic = "Competition Math"
    if topics and isinstance(topics[0], str):
        # Keep broad topics searchable, rather than copying the full taxonomy.
        parts = [part.strip() for part in topics[0].split(">")]
        topic = parts[1] if parts[0] == "Discrete Mathematics" and len(parts) > 1 else parts[0]
        topic = topic[:120] or "Competition Math"
    competition = row.get("competition") or "Competition math"
    country = row.get("country") or ""
    credit = f"{competition}, {country}" if country else competition
    source = f"Source: {credit} (MathNet #{source_id})."
    try:
        return QuestionCreate(
            topic=topic,
            text=f"{text.strip()}\n\n{source}",
            correct_answer=[answer],
            explanation=(
                f"{explanation.strip()}\n\n{source}\n"
                f"MathNet, Alshammari et al. (2026). {DATASET_URL}\n"
                "License: https://creativecommons.org/licenses/by/4.0/ . "
                "Original competition copyrights are retained; see the dataset license.\n"
                "Imported for final-answer practice; original competitions may require a proof."
            ),
        )
    except ValidationError:
        return None


def import_online(
    db: Session, limit: int = 500, *, progress: Callable[[str], None] | None = None
) -> int:
    if limit < 1:
        raise ValueError("Limit must be positive")
    existing = db.execute(select(Question.text, Question.explanation)).all()
    seen = {
        source_id
        for text, explanation in existing
        for source_id in SOURCE_ID.findall(f"{text}\n{explanation or ''}")
    }
    problems = []
    scanned = 0
    for rows in fetch_batches():
        for row in rows:
            if str(row.get("id")) in seen:
                continue
            problem = convert(row)
            if problem is None:
                continue
            seen.add(str(row["id"]))
            problems.append(problem)
            if len(problems) == limit:
                break
        scanned += len(rows)
        if progress:
            progress(f"Scanned {scanned} rows; selected {len(problems)} new problems.")
        if len(problems) == limit:
            break
    # No writes until all required network requests have succeeded.
    db.add_all(Question(**problem.model_dump()) for problem in problems)
    db.commit()
    return len(problems)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=500, help="Number of new problems to import")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    create_tables()
    try:
        with SessionLocal() as db:
            added = import_online(
                db, args.limit, progress=lambda message: print(message, flush=True)
            )
    except ModuleNotFoundError:
        parser.exit(1, "Install the import dependency: pip install -r requirements-import.txt\n")
    except (URLError, TimeoutError, ValueError, KeyError) as exc:
        parser.exit(1, f"Online import failed; no problems were saved: {exc}\n")
    print(f"Imported {added} new MathNet problems. Refresh the website to see them.")


if __name__ == "__main__":
    main()
