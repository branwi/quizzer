import io
import json
from urllib.error import HTTPError, URLError

import pytest
from sqlalchemy import func, select

from backend import import_online as online
from backend.models import Question


def row(source_id="abc", **changes):
    return {
        "id": source_id,
        "language": "English",
        "problem_type": "proof and answer",
        "problem_markdown": "Find the value of $2+2$.",
        "final_answer": "4",
        "solutions_markdown": ["$2+2=4$."],
        "competition": "Example competition",
        "country": "Example",
        "topics_flat": ["Algebra > Prealgebra"],
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"language": "Spanish"},
        {"final_answer": None},
        {"final_answer": "x=4"},
        {"final_answer": "4, 5"},
        {"problem_type": "proof only"},
        {"problem_markdown": "Find x. ![](attached_image_1.png)"},
        {"problem_markdown": "Use the diagram below."},
        {"problem_markdown": "x" * 10001},
    ],
)
def test_unusable_problems_are_skipped(changes):
    assert online.convert(row(**changes)) is None


def test_conversion_preserves_math_and_attribution_and_omits_missing_solution_images():
    problem = online.convert(row(solutions_markdown=["![](attached_image_2.png)", "$2+2=4$."]))
    assert "$2+2$" in problem.text
    assert "MathNet #abc" in problem.text
    assert problem.correct_answer == ["4"]
    assert "attached_image" not in problem.explanation
    assert online.DATASET_URL in problem.explanation
    assert "creativecommons.org/licenses/by/4.0/" in problem.explanation


def test_paging_limit_deduplication_and_existing_data(db, monkeypatch):
    db.add(
        Question(
            topic="Existing",
            text="Keep me",
            correct_answer=["1"],
        )
    )
    db.commit()
    batches = [[row(), row("bad", language="Spanish")], [row("abc"), row("def")]]
    monkeypatch.setattr(online, "fetch_batches", lambda: iter(batches))
    assert online.import_online(db, limit=2) == 2
    assert online.import_online(db, limit=2) == 0
    assert db.scalar(select(func.count()).select_from(Question)) == 3


def test_network_failure_does_not_save_partial_batch(db, monkeypatch):
    def fetch():
        yield [row()]
        raise URLError("offline")

    monkeypatch.setattr(online, "fetch_batches", fetch)
    with pytest.raises(URLError):
        online.import_online(db, limit=2)
    assert db.scalar(select(func.count()).select_from(Question)) == 0


def test_online_problem_can_be_answered_through_existing_api(db, client, student, monkeypatch):
    monkeypatch.setattr(online, "fetch_batches", lambda: iter([[row()]]))
    assert online.import_online(db, limit=1) == 1
    problem = client.get("/api/bank/questions").json()[0]
    assert "correct_answer" not in problem
    assert "type" not in problem and "choices" not in problem
    result = client.post(f"/api/bank/questions/{problem['id']}/check", json={"response": "4"})
    assert result.json()["is_correct"] is True


def test_bulk_download_reads_text_columns_without_decoding_images(monkeypatch):
    arrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    buffer = io.BytesIO()
    parquet.write_table(arrow.Table.from_pylist([{**row(), "images": [b"not an image"]}]), buffer)
    calls = []

    def download(url):
        calls.append(url)
        if url == online.FILES_API:
            return json.dumps(
                [
                    {"type": "file", "path": "data/all/train-00000.parquet"},
                    {"type": "file", "path": "data/all/README.md"},
                ]
            ).encode()
        return buffer.getvalue()

    monkeypatch.setattr(online, "download", download)
    batches = list(online.fetch_batches())
    assert batches == [[row()]]
    assert len(calls) == 2
    assert calls[1].endswith("/resolve/main/data/all/train-00000.parquet")


def test_download_backs_off_when_rate_limited(monkeypatch):
    attempts = []
    delays = []

    def open_url(request, **kwargs):
        attempts.append(request.full_url)
        if len(attempts) == 1:
            raise HTTPError(request.full_url, 429, "Slow down", {"Retry-After": "3"}, None)
        return io.BytesIO(b"[]")

    monkeypatch.setattr(online, "urlopen", open_url)
    monkeypatch.setattr(online.time, "sleep", delays.append)
    assert online.download(online.FILES_API) == b"[]"
    assert len(attempts) == 2
    assert delays == [3]
