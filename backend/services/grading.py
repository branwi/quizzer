"""Compare a single response with the question's accepted answer; save nothing."""


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def grade(accepted_answers: list[str], response: object) -> bool:
    if not isinstance(response, str) or not response.strip():
        return False
    return normalize(response) in {normalize(answer) for answer in accepted_answers}
