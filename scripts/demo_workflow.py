"""Exercise the running API with seeded accounts; add fresh demo content on every run."""

import argparse
import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4

DEMO_PASSWORD = "quiz-demo-password"


class Client:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def call(self, method: str, path: str, data=None, *, expected=200):
        request = Request(
            self.base_url + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json"} if data is not None else {},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                status, body = response.status, response.read()
        except HTTPError as exc:
            status, body = exc.code, exc.read()
        result = json.loads(body) if body else None
        if status != expected:
            detail = result.get("detail") if isinstance(result, dict) else "Unexpected response"
            raise RuntimeError(f"{method} {path}: expected {expected}, got {status}: {detail}")
        return result

    def login(self, email: str) -> None:
        self.call("POST", "/api/auth/login", {"email": email, "password": DEMO_PASSWORD})


def assert_safe(value) -> None:
    if isinstance(value, dict):
        if {"correct_answer", "explanation"} & value.keys():
            raise RuntimeError("An in-progress student response contained an answer key")
        for child in value.values():
            assert_safe(child)
    elif isinstance(value, list):
        for child in value:
            assert_safe(child)


def run(base_url: str) -> dict:
    teacher, student = Client(base_url), Client(base_url)
    teacher.call("GET", "/health")
    teacher.login("teacher@example.test")
    student.login("bob@example.test")
    student_id = student.call("GET", "/api/me")["id"]
    teacher.call("GET", "/api/students")
    tag = "API demo " + uuid4().hex[:8]
    contents = [
        {
            "type": "mcq",
            "text": f"{tag}: What is 2 + 2?",
            "topic": "Math",
            "choices": [{"id": "a", "text": "Four"}, {"id": "b", "text": "Five"}],
            "correct_answer": "a",
            "explanation": "Two plus two is four.",
            "is_public": True,
        },
        {
            "type": "true_false",
            "text": f"{tag}: Two is even.",
            "topic": "Math",
            "correct_answer": True,
            "explanation": "Two is divisible by two.",
            "is_public": True,
        },
        {
            "type": "short_answer",
            "text": f"{tag}: What is 2 + 2?",
            "topic": "Math",
            "correct_answer": ["4", "four"],
            "explanation": "Four.",
            "is_public": False,
        },
    ]
    sources = [teacher.call("POST", "/api/questions", data, expected=201) for data in contents]
    quiz = teacher.call(
        "POST",
        "/api/quizzes",
        {
            "title": tag,
            "questions": [
                {"question_id": question["id"], "points": points}
                for question, points in zip(sources, (2, 3, 5), strict=True)
            ],
        },
        expected=201,
    )
    path = f"/api/quizzes/{quiz['id']}"
    teacher.call("POST", path + "/publish")
    teacher.call("POST", path + "/assignments", {"student_ids": [student_id]})
    # A later edit changes the bank while the assigned quiz keeps the original question/key.
    teacher.call(
        "PUT",
        f"/api/questions/{sources[0]['id']}",
        {
            **contents[0],
            "text": f"{tag}: What is 2 + 3?",
            "correct_answer": "b",
            "explanation": "Two plus three is five.",
        },
    )
    assert_safe(student.call("GET", "/api/quizzes/assigned"))
    assert_safe(student.call("GET", path))
    active = student.call("POST", path + "/attempts", expected=201)
    assert_safe(active)
    resumed = student.call("POST", path + "/attempts")
    if resumed["id"] != active["id"]:
        raise RuntimeError("Repeated start did not resume the open attempt")
    submission = {
        "answers": [
            {"quiz_question_id": question["id"], "response": response}
            for question, response in zip(active["questions"], ("a", True, "  FOUR\t"), strict=True)
        ]
    }
    attempt_path = f"/api/attempts/{active['id']}"
    review = student.call("POST", attempt_path + "/submit", submission)
    student.call("GET", attempt_path)
    student.call("POST", attempt_path + "/submit", submission, expected=409)
    student.call("POST", path + "/attempts", expected=409)
    teacher.call("GET", path + "/results")
    bank = student.call("GET", "/api/bank/questions?" + urlencode({"q": tag}))
    assert_safe(bank)
    practice = student.call(
        "POST",
        "/api/quizzes/practice",
        {
            "title": tag + " practice",
            "question_ids": [q["id"] for q in bank["items"]],
        },
        expected=201,
    )
    assert_safe(practice)
    practice_attempt = student.call("POST", f"/api/quizzes/{practice['id']}/attempts", expected=201)
    practice_review = student.call(
        "POST",
        f"/api/attempts/{practice_attempt['id']}/submit",
        {
            "answers": [
                {
                    "quiz_question_id": q["id"],
                    "response": "b" if q["content"]["type"] == "mcq" else True,
                }
                for q in practice_attempt["questions"]
            ]
        },
    )
    if review["score"] != 10 or practice_review["score"] != 2:
        raise RuntimeError("Demo grading did not match the expected scores")
    student.call("POST", "/api/auth/logout", expected=204)
    student.call("GET", "/api/me", expected=401)
    return {
        "assigned_quiz_id": quiz["id"],
        "assigned_attempt_id": active["id"],
        "assigned_score": review["score"],
        "assigned_max_score": review["max_score"],
        "practice_quiz_id": practice["id"],
        "practice_attempt_id": practice_attempt["id"],
        "practice_score": practice_review["score"],
        "practice_max_score": practice_review["max_score"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--json", action="store_true", help="Print result ids/scores as JSON")
    args = parser.parse_args()
    try:
        result = run(args.base_url)
    except (RuntimeError, URLError) as exc:
        raise SystemExit(
            f"Demo failed: {exc}. Start the server and run python -m scripts.seed."
        ) from None
    if args.json:
        print(json.dumps(result))
    else:
        print(
            f"Assigned quiz {result['assigned_quiz_id']}: 10/10; "
            f"practice quiz {result['practice_quiz_id']}: 2/2."
        )
        print("Verified snapshots, safe responses, resume, review, results, limits, and logout.")
        print("Fresh demo questions, quizzes, and attempts were added to the local database.")


if __name__ == "__main__":
    main()
