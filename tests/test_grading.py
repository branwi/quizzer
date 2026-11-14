import pytest

from backend.services.grading import grade, normalize


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
def test_whitespace_case_and_aliases(response, expected):
    assert grade(["New York", "NYC", "Straße"], response) is expected


def test_grading_does_not_mutate_accepted_answers():
    answers = ["FOUR", "4"]
    assert grade(answers, "four") is True
    assert answers == ["FOUR", "4"]
    assert normalize("  Hello\t WORLD\n") == "hello world"
