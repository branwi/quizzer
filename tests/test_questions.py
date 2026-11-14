import pytest


def test_teacher_can_manage_short_answer_questions(client, teacher, short_answer):
    payload = {**short_answer, "text": " A prompt ", "topic": " Math "}
    response = client.post("/api/questions", json=payload)
    assert response.status_code == 201, response.text
    question = response.json()
    assert question["text"] == "A prompt" and question["topic"] == "Math"
    assert question["correct_answer"] == ["four", "4"]
    assert set(question) == {"id", "text", "topic", "correct_answer", "explanation"}
    path = f"/api/questions/{question['id']}"
    assert client.get(path).json() == question
    assert client.get("/api/questions").json() == [question]
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get("/api/questions").json() == []


def test_full_replacement_clears_explanation_and_validates_before_writing(
    client, teacher, short_answer
):
    question = client.post("/api/questions", json=short_answer).json()
    path = f"/api/questions/{question['id']}"
    assert client.put(path, json={**short_answer, "correct_answer": []}).status_code == 422
    assert client.get(path).json() == question
    payload = {"text": "Name the sum", "topic": "Math", "correct_answer": [" four "]}
    result = client.put(path, json=payload)
    assert result.status_code == 200
    assert result.json()["correct_answer"] == ["four"]
    assert result.json()["explanation"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"correct_answer": "four"},
        {"correct_answer": True},
        {"correct_answer": []},
        {"correct_answer": [" "]},
        {"correct_answer": [4]},
        {"correct_answer": [True]},
        {"correct_answer": ["x" * 2001]},
        {"correct_answer": ["four"] * 101},
        {"text": " "},
        {"topic": " "},
        {"type": "short_answer"},
        {"type": "mcq"},
        {"type": "true_false"},
        {"choices": []},
    ],
)
def test_invalid_questions_are_rejected(client, teacher, short_answer, changes):
    assert client.post("/api/questions", json={**short_answer, **changes}).status_code == 422
    assert client.get("/api/questions").json() == []


def test_student_cannot_manage_bank_or_see_teacher_answers(client, student, short_answer):
    for method, path in [
        ("GET", "/api/questions"),
        ("POST", "/api/questions"),
        ("GET", "/api/questions/1"),
        ("PUT", "/api/questions/1"),
        ("DELETE", "/api/questions/1"),
    ]:
        response = client.request(
            method, path, json=short_answer if method in ("POST", "PUT") else None
        )
        assert response.status_code == 403
        assert "correct_answer" not in response.text


def test_teacher_keeps_access_to_bank_after_logging_in_again(
    client, teacher, short_answer, teacher_profile
):
    question = client.post("/api/questions", json=short_answer).json()
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json=teacher_profile)
    assert client.get("/api/questions").json() == [question]
    assert (
        client.put(
            f"/api/questions/{question['id']}", json={**short_answer, "topic": "New"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("question_id", [0, -1, 2**63, "bad"])
def test_bad_question_ids_are_rejected(client, teacher, question_id):
    assert client.get(f"/api/questions/{question_id}").status_code == 422
