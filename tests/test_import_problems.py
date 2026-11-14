import json

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.import_problems import import_problems
from backend.models import AssignedProblem, Question


def test_import_preserves_existing_questions_and_assignments_and_skips_repeats(db, assigned):
    original = db.get(Question, assigned["question"]["id"])
    assert import_problems(db) == (12, 0)
    assert import_problems(db) == (0, 12)
    assert db.scalar(select(func.count()).select_from(Question)) == 13
    assert db.get(Question, original.id).text == original.text
    assert db.scalar(select(func.count()).select_from(AssignedProblem)) == 1


def test_invalid_batch_writes_nothing(db, tmp_path, short_answer):
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps([short_answer, {**short_answer, "correct_answer": "missing"}]), encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        import_problems(db, path)
    assert db.scalar(select(func.count()).select_from(Question)) == 0


def test_imported_questions_can_be_practiced_through_existing_api(db, client, student):
    import_problems(db)
    questions = client.get("/api/bank/questions").json()
    assert len(questions) == 12
    for question in questions:
        assert "NZMOC" in question["text"]
        assert "correct_answer" not in question
        stored = db.get(Question, question["id"])
        path = f"/api/bank/questions/{question['id']}/check"
        result = client.post(path, json={"response": stored.correct_answer[0]})
        assert result.status_code == 200
        assert result.json()["is_correct"] is True
        assert "https://creativecommons.org/licenses/by/4.0/" in result.json()["explanation"]
        assert client.post(path, json={"response": "wrong"}).json()["is_correct"] is False
