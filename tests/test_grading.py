from copy import deepcopy

import pytest

from app.services.grading import grade, normalize


@pytest.mark.parametrize(
    "response,expected",
    [
        ("a", True),
        ("b", False),
        ("A", False),
        (" a ", False),
        ("", False),
        (None, False),
        (True, False),
        (1, False),
        (["a"], False),
        ({}, False),
    ],
)
def test_mcq(response, expected):
    assert grade({"type": "mcq", "correct_answer": "a"}, response) is expected


@pytest.mark.parametrize("key", [True, False])
@pytest.mark.parametrize("response", [True, False, 1, 0, "true", "false", "", None, [], {}])
def test_true_false_never_coerces_numbers_or_strings(key, response):
    assert grade({"type": "true_false", "correct_answer": key}, response) is (
        type(response) is bool and response is key
    )


@pytest.mark.parametrize(
    "response,expected",
    [
        ("New York", True),
        ("NEW YORK", True),
        (" new   york\t\n", True),
        ("NYC", True),
        ("StraSSe", True),
        ("newyork", False),
        ("New York!", False),
        ("", False),
        (" \t\n", False),
        (None, False),
        (4, False),
        (True, False),
        (["NYC"], False),
        ({"text": "NYC"}, False),
    ],
)
def test_short_answer_whitespace_case_and_aliases(response, expected):
    question = {"type": "short_answer", "correct_answer": ["New York", "NYC", "Straße"]}
    assert grade(question, response) is expected


def test_grading_does_not_mutate_question():
    question = {"type": "short_answer", "correct_answer": ["FOUR"], "explanation": "Keep me"}
    original = deepcopy(question)
    assert grade(question, "four") is True
    assert question == original
    assert normalize("  Hello\t WORLD\n") == "hello world"


@pytest.mark.parametrize("question", [{"type": "essay"}, {}])
def test_unsupported_question_type_fails_explicitly(question):
    with pytest.raises(ValueError, match="question type"):
        grade(question, "answer")
