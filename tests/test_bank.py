import pytest
from sqlalchemy import func, select

from backend.database import Base


def test_bank_filters_and_assigned_lists_hide_answer_keys(client, assigned, teacher_profile):
    question = assigned["question"]
    for path in (
        "/api/bank/questions",
        "/api/assignments",
        f"/api/bank/questions/{question['id']}",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert "correct_answer" not in response.text and "explanation" not in response.text
    assert client.get("/api/bank/questions").json() == client.get("/api/assignments").json()
    client.post("/api/auth/login", json=teacher_profile)
    client.post(
        "/api/questions",
        json={
            "text": "100% under_score",
            "topic": "Logic",
            "correct_answer": ["100"],
        },
    )
    assert len(client.get("/api/bank/questions", params={"topic": "Math"}).json()) == 1
    assert len(client.get("/api/bank/questions", params={"topic": "Logic"}).json()) == 1


def test_answer_check_is_repeatable_and_never_saves_history(client, assigned, db):
    question = assigned["question"]
    path = f"/api/bank/questions/{question['id']}/check"
    before = {
        table.name: db.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }
    for answer, expected in [("five", False), ("4", True), (None, False), ("FOUR", True)]:
        result = client.post(path, json={"response": answer})
        assert result.status_code == 200, result.text
        assert result.json() == {
            "question_id": question["id"],
            "is_correct": expected,
            "correct_answer": ["four", "4"],
            "explanation": question["explanation"],
        }
    after = {
        table.name: db.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }
    assert after == before
    assert len(client.get("/api/assignments").json()) == 1


@pytest.mark.parametrize("response", [True, False, 1, [], {}, "x" * 2001])
def test_bad_responses_return_validation_error(client, assigned, response):
    path = f"/api/bank/questions/{assigned['question']['id']}/check"
    assert client.post(path, json={"response": response}).status_code == 422


@pytest.mark.parametrize(
    "answers,response,expected",
    [
        (["New York", "NYC"], " new   YORK ", True),
        (["NYC"], "London", False),
        (["true"], "TRUE", True),
        (["4"], "", False),
        (["4"], None, False),
    ],
)
def test_check_short_answers(client, teacher, answers, response, expected):
    question = client.post(
        "/api/questions",
        json={"text": "Question", "topic": "General", "correct_answer": answers},
    ).json()
    client.post("/api/auth/login", json={"first_name": "Sam", "grade": "K"})
    result = client.post(f"/api/bank/questions/{question['id']}/check", json={"response": response})
    assert result.status_code == 200
    assert result.json()["is_correct"] is expected
