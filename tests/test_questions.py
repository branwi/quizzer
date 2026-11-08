import pytest

QUESTION_TYPES = [
    {
        "type": "mcq",
        "choices": [{"id": "a", "text": "Yes"}, {"id": "b", "text": "No"}],
        "correct_answer": "a",
    },
    {"type": "true_false", "correct_answer": False},
    {"type": "short_answer", "correct_answer": ["four", "4"]},
]


@pytest.mark.parametrize("content", QUESTION_TYPES)
def test_teacher_can_manage_each_question_type(client, teacher, content):
    payload = {"text": " A prompt ", "topic": " Math ", **content}
    response = client.post("/api/questions", json=payload)
    assert response.status_code == 201, response.text
    question = response.json()
    assert question["text"] == "A prompt" and question["topic"] == "Math"
    assert question["correct_answer"] == content["correct_answer"]
    path = f"/api/questions/{question['id']}"
    assert client.get(path).json() == question
    assert client.get("/api/questions").json() == [question]
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get("/api/questions").json() == []


def test_full_replacement_clears_old_type_fields_and_validates_before_writing(client, teacher, mcq):
    question = client.post("/api/questions", json=mcq).json()
    path = f"/api/questions/{question['id']}"
    assert client.put(path, json={**mcq, "correct_answer": "bad"}).status_code == 422
    assert client.get(path).json() == question
    payload = {
        "type": "short_answer",
        "text": "Name the sum",
        "topic": "Math",
        "correct_answer": ["four"],
    }
    result = client.put(path, json=payload)
    assert result.status_code == 200
    assert result.json()["choices"] is None and result.json()["explanation"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"choices": []},
        {"choices": [{"id": "a", "text": "A"}, {"id": "a", "text": "B"}]},
        {"correct_answer": "missing"},
        {"correct_answer": True},
        {"text": " "},
        {"topic": " "},
        {"type": "essay"},
    ],
)
def test_invalid_questions_are_rejected(client, teacher, mcq, changes):
    assert client.post("/api/questions", json={**mcq, **changes}).status_code == 422
    assert client.get("/api/questions").json() == []


@pytest.mark.parametrize("answer", [1, "true", None])
def test_true_false_requires_boolean_answer(client, teacher, answer):
    payload = {"type": "true_false", "text": "True?", "topic": "Logic", "correct_answer": answer}
    assert client.post("/api/questions", json=payload).status_code == 422


def test_student_cannot_manage_bank_or_see_teacher_answers(client, student, mcq):
    for method, path in [
        ("GET", "/api/questions"),
        ("POST", "/api/questions"),
        ("GET", "/api/questions/1"),
        ("PUT", "/api/questions/1"),
        ("DELETE", "/api/questions/1"),
    ]:
        response = client.request(method, path, json=mcq if method in ("POST", "PUT") else None)
        assert response.status_code == 403
        assert "correct_answer" not in response.text


def test_teacher_keeps_access_to_bank_after_logging_in_again(client, teacher, mcq, teacher_profile):
    question = client.post("/api/questions", json=mcq).json()
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json=teacher_profile)
    assert client.get("/api/questions").json() == [question]
    assert (
        client.put(f"/api/questions/{question['id']}", json={**mcq, "topic": "New"}).status_code
        == 200
    )


@pytest.mark.parametrize("question_id", [0, -1, 2**63, "bad"])
def test_bad_question_ids_are_rejected(client, teacher, question_id):
    assert client.get(f"/api/questions/{question_id}").status_code == 422
