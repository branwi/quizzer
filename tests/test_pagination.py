import pytest

from backend.models import Question


@pytest.fixture
def bank(db):
    questions = [
        Question(
            text=f"Question {n}",
            topic="Algebra" if n % 2 == 0 else "Number Theory",
            correct_answer=[str(n)],
            explanation="An answer explanation.",
        )
        for n in range(1, 46)
    ]
    db.add_all(questions)
    db.commit()
    return [question.id for question in questions]


@pytest.mark.parametrize("path", ["/api/questions", "/api/bank/questions"])
def test_bank_pages_are_bounded_ordered_and_have_totals(client, teacher, bank, path):
    ids = []
    for page, expected_size in [(1, 20), (2, 20), (3, 5)]:
        response = client.get(path, params={"page": page})
        assert response.status_code == 200
        assert response.headers["X-Total-Count"] == "45"
        assert response.headers["X-Page"] == str(page)
        assert len(response.json()) == expected_size
        ids.extend(question["id"] for question in response.json())
    assert ids == bank
    assert len(client.get(path).json()) == 20


def test_filters_count_only_matching_results_and_keep_student_answers_hidden(
    client, student, bank
):
    response = client.get(
        "/api/bank/questions",
        params={
            "topic": "Algebra",
            "page": 2,
        },
    )
    assert response.headers["X-Total-Count"] == "22"
    assert [q["id"] for q in response.json()] == [bank[41], bank[43]]
    assert "correct_answer" not in response.text and "explanation" not in response.text
    empty = client.get("/api/bank/questions", params={"topic": "Missing topic", "page": 9})
    assert empty.json() == []
    assert empty.headers["X-Total-Count"] == "0"
    assert empty.headers["X-Page"] == "1"


def test_out_of_range_page_clamps_after_last_item_is_deleted(client, teacher, bank):
    path = "/api/questions"
    response = client.get(path, params={"page": 999, "page_size": 11})
    assert response.headers["X-Page"] == "5"
    assert [q["id"] for q in response.json()] == [bank[-1]]
    assert client.delete(f"{path}/{bank[-1]}").status_code == 204
    response = client.get(path, params={"page": 5, "page_size": 11})
    assert response.headers["X-Page"] == "4"
    assert response.headers["X-Total-Count"] == "44"
    assert len(response.json()) == 11


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"page": 2**31},
        {"page": "bad"},
        {"page_size": 0},
        {"page_size": 101},
        {"q": "Question"},
        {"type": "short_answer"},
    ],
)
@pytest.mark.parametrize("path", ["/api/questions", "/api/bank/questions"])
def test_invalid_filters_are_rejected(client, teacher, params, path):
    assert client.get(path, params=params).status_code == 422


def test_topic_choices_include_topics_beyond_first_page(client, student, bank, db):
    db.get(Question, bank[-1]).topic = "Combinatorics"
    db.commit()
    response = client.get("/api/bank/questions/topics")
    assert response.status_code == 200
    assert response.json() == ["Algebra", "Combinatorics", "Number Theory"]
    filtered = client.get("/api/bank/questions", params={"topic": "Combinatorics"})
    assert [q["id"] for q in filtered.json()] == [bank[-1]]


def test_topic_choices_require_login(client):
    assert client.get("/api/bank/questions/topics").status_code == 401
