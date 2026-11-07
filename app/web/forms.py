import json
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, TypeAdapter, ValidationError

from app.schemas import QuestionCreate
from app.workflow_schemas import Id, QuizCreate


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Id
    points: Annotated[StrictInt, Field(ge=1, le=1000000)] = 1


def selected(form, *, limit=100) -> list[Selection]:
    try:
        return _selected(form, limit=limit)
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(
            422, f"Choose up to {limit} valid, unique items and try again."
        ) from None


def _selected(form, *, limit=100) -> list[Selection]:
    raw = form.get("selection", "")
    if raw:
        if not isinstance(raw, str) or len(raw) > 40000:
            raise ValueError("Choose fewer items and try again.")
        values = json.loads(raw)
    else:
        values = [
            {"id": int(value), "points": int(form.get(f"points_{value}", 1))}
            for value in form.getlist("selected_ids")
        ]
    if not isinstance(values, list) or len(values) > limit:
        raise ValueError(f"Select at most {limit} items.")
    result = TypeAdapter(list[Selection]).validate_python(values)
    if len({item.id for item in result}) != len(result):
        raise ValueError("Each item can be selected only once.")
    return result


def question_payload(form) -> dict:
    kind = form.get("type", "mcq")
    common = {
        "type": kind,
        "text": form.get("text", ""),
        "topic": form.get("topic", ""),
        "explanation": form.get("explanation") or None,
        "is_public": form.get("is_public") == "on",
    }
    if kind == "mcq":
        choices = [
            {
                "id": form.get(f"choice_id_{i}", chr(97 + i)),
                "text": form.get(f"choice_text_{i}", ""),
            }
            for i in range(6)
            if str(form.get(f"choice_text_{i}", "")).strip()
        ]
        index = int(form.get("correct_choice", -1))
        answer = form.get(f"choice_id_{index}", chr(97 + index)) if 0 <= index < 6 else ""
        common.update(choices=choices, correct_answer=answer)
    elif kind == "true_false":
        value = form.get("true_false_answer")
        if value not in ("true", "false"):
            raise ValueError("Choose True or False as the correct answer.")
        common["correct_answer"] = value == "true"
    else:
        common["correct_answer"] = [
            line.strip()
            for line in str(form.get("accepted_answers", "")).splitlines()
            if line.strip()
        ]
    return common


def question_data(form):
    return TypeAdapter(QuestionCreate).validate_python(question_payload(form))


def question_values(question=None, form=None) -> dict:
    if form is not None:
        return dict(form)
    values = {"type": "mcq", "correct_choice": "0", "true_false_answer": "true"}
    for i in range(6):
        values[f"choice_id_{i}"] = chr(97 + i)
    if question is None:
        return values
    values.update(question.model_dump())
    values["is_public"] = "on" if question.is_public else ""
    if question.type == "mcq":
        for i, choice in enumerate(question.choices):
            values[f"choice_id_{i}"], values[f"choice_text_{i}"] = choice.id, choice.text
            if choice.id == question.correct_answer:
                values["correct_choice"] = str(i)
    elif question.type == "true_false":
        values["true_false_answer"] = "true" if question.correct_answer else "false"
    else:
        values["accepted_answers"] = "\n".join(question.correct_answer)
    return values


def quiz_data(form) -> QuizCreate:
    due = form.get("due_at", "")
    return QuizCreate.model_validate(
        {
            "title": form.get("title", ""),
            "questions": [
                {"question_id": item.id, "points": item.points} for item in selected(form)
            ],
            "due_at": due + "Z" if due else None,
            "max_attempts": int(form["max_attempts"]) if form.get("max_attempts") else None,
        }
    )


def messages(exc) -> list[str]:
    if isinstance(exc, ValidationError):
        return [
            " · ".join(str(part) for part in error["loc"]) + ": " + error["msg"]
            for error in exc.errors()
        ]
    return [str(exc) or "Check the form and try again."]
