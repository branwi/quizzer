from datetime import timedelta

from app.database import utc_now
from app.models import Attempt


def test_empty_analytics_and_permissions(client, workflow):
    path = f"/api/quizzes/{workflow['quiz_id']}/analytics"
    assert client.get(path).status_code == 403
    client.post("/api/auth/login", json=workflow["teacher_credentials"])
    response = client.get(path)
    assert response.status_code == 200
    data = response.json()
    assert data["submitted_attempts"] == data["total_attempts"] == 0
    assert data["average_percent"] is None
    assert all(q["accuracy"] is None and q["responses"] == 0 for q in data["questions"])
    assert [bucket["count"] for bucket in data["score_distribution"]] == [0] * 5
    other = {"email": "other-analytics@example.test", "password": "other-password"}
    client.post("/api/auth/register", json={**other, "name": "Other", "role": "teacher"})
    client.post("/api/auth/login", json=other)
    assert client.get(path).status_code == 404


def test_analytics_only_submitted_attempts_and_frozen_prompts(client, workflow):
    active = client.post(f"/api/quizzes/{workflow['quiz_id']}/attempts").json()
    client.post(
        f"/api/attempts/{active['id']}/submit",
        json={
            "answers": [
                {"quiz_question_id": q["id"], "response": response}
                for q, response in zip(active["questions"], ("a", False, "four"), strict=True)
            ]
        },
    )
    client.post("/api/auth/login", json=workflow["teacher_credentials"])
    data = client.get(f"/api/quizzes/{workflow['quiz_id']}/analytics").json()
    assert data["average_percent"] == data["lowest_percent"] == data["highest_percent"] == 70
    assert data["submitted_attempts"] == 1
    assert [q["accuracy"] for q in data["questions"]] == [1.0, 0.0, 1.0]
    assert [bucket["count"] for bucket in data["score_distribution"]] == [0, 0, 0, 1, 0]
    client.delete(f"/api/questions/{workflow['questions'][0]['id']}")
    after = client.get(f"/api/quizzes/{workflow['quiz_id']}/analytics").json()
    assert after == data


def test_score_bucket_boundaries_and_in_progress_exclusion(client, workflow, db):
    now = utc_now()
    db.add_all(
        [
            Attempt(
                quiz_id=workflow["quiz_id"],
                student_id=workflow["student"]["id"],
                started_at=now - timedelta(minutes=1),
                submitted_at=now,
                score=score,
                max_score=10,
            )
            for score in (0, 2, 4, 6, 8, 10)
        ]
    )
    db.add(Attempt(quiz_id=workflow["quiz_id"], student_id=workflow["student"]["id"], max_score=10))
    db.commit()
    client.post("/api/auth/login", json=workflow["teacher_credentials"])
    data = client.get(f"/api/quizzes/{workflow['quiz_id']}/analytics").json()
    assert [b["count"] for b in data["score_distribution"]] == [1, 1, 1, 1, 2]
    assert data["submitted_attempts"] == 6
    assert data["in_progress_attempts"] == 1
    assert data["total_attempts"] == 7
    assert data["average_percent"] == 50
    assert data["lowest_percent"] == 0
    assert data["highest_percent"] == 100
