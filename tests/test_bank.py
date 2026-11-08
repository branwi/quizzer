import pytest
from sqlalchemy import func, select

from app.database import Base


def test_bank_search_and_assigned_lists_hide_answer_keys(client, assigned, teacher_profile):
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
            "type": "true_false",
            "text": "100% under_score",
            "topic": "Logic",
            "correct_answer": True,
        },
    )
    for query in ("logic", "%", "_"):
        assert len(client.get("/api/bank/questions", params={"q": query}).json()) == 1
    assert len(client.get("/api/bank/questions", params={"topic": "Math"}).json()) == 1
    assert len(client.get("/api/bank/questions", params={"type": "true_false"}).json()) == 1
    assert client.get("/api/bank/questions", params={"type": "essay"}).status_code == 422


def test_answer_check_is_repeatable_and_never_saves_history(client, assigned, db):
    question = assigned["question"]
    path = f"/api/bank/questions/{question['id']}/check"
    before = {
        table.name: db.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }
    for answer, expected in [("b", False), ("a", True), (None, False), ("a", True)]:
        result = client.post(path, json={"response": answer})
        assert result.status_code == 200, result.text
        assert result.json() == {
            "question_id": question["id"],
            "is_correct": expected,
            "correct_answer": "a",
            "explanation": question["explanation"],
        }
    after = {
        table.name: db.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }
    assert after == before
    assert len(client.get("/api/assignments").json()) == 1


@pytest.mark.parametrize("response", [True, 1, "not-a-choice", [], {}])
def test_bad_responses_return_validation_error(client, assigned, response):
    path = f"/api/bank/questions/{assigned['question']['id']}/check"
    assert client.post(path, json={"response": response}).status_code == 422


@pytest.mark.parametrize(
    "content,response,expected",
    [
        ({"type": "true_false", "correct_answer": True}, True, True),
        ({"type": "true_false", "correct_answer": True}, False, False),
        ({"type": "true_false", "correct_answer": True}, "true", None),
        ({"type": "short_answer", "correct_answer": ["New York", "NYC"]}, " new   YORK ", True),
        ({"type": "short_answer", "correct_answer": ["NYC"]}, "London", False),
    ],
)
def test_check_answer_types(client, teacher, content, response, expected):
    question = client.post(
        "/api/questions", json={"text": "Question", "topic": "General", **content}
    ).json()
    client.post("/api/auth/login", json={"first_name": "Sam", "grade": "K"})
    result = client.post(f"/api/bank/questions/{question['id']}/check", json={"response": response})
    if expected is None:
        assert result.status_code == 422
    else:
        assert result.status_code == 200
        assert result.json()["is_correct"] is expected
