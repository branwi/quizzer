"""Compare a single response with the question's accepted answer; save nothing."""

from collections.abc import Mapping
from typing import Any


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def grade_mcq(question: Mapping[str, Any], response: object) -> bool:
    return isinstance(response, str) and response == question["correct_answer"]


def grade_true_false(question: Mapping[str, Any], response: object) -> bool:
    # bool subclasses int in Python; 0/1 must not silently become correct answers.
    return type(response) is bool and response is question["correct_answer"]


def grade_short_answer(question: Mapping[str, Any], response: object) -> bool:
    if not isinstance(response, str) or not response.strip():
        return False
    return normalize(response) in {normalize(answer) for answer in question["correct_answer"]}


GRADERS = {
    "mcq": grade_mcq,
    "true_false": grade_true_false,
    "short_answer": grade_short_answer,
}


def grade(question: Mapping[str, Any], response: object) -> bool:
    try:
        grader = GRADERS[question["type"]]
    except KeyError:
        raise ValueError("Unsupported or missing question type") from None
    return grader(question, response)
