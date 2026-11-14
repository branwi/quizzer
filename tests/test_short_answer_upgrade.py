import pytest
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from backend.database import create_tables, make_engine
from backend.models import AssignedProblem, Question, Role, User


@pytest.fixture
def old_database(tmp_path):
    engine = make_engine("sqlite:///" + (tmp_path / "legacy.db").as_posix())
    create_tables(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE problems ADD COLUMN type VARCHAR(20) NOT NULL DEFAULT 'short_answer'"
        )
        connection.exec_driver_sql("ALTER TABLE problems ADD COLUMN choices JSON")
    with Session(engine) as db:
        db.add(User(id=7, first_name="Maya", grade="6", role=Role.STUDENT))
        db.add(
            Question(
                id=42,
                text="What is 2 + 2?",
                topic="Math",
                correct_answer=["4", "four"],
                explanation="Two plus two equals four.",
            )
        )
        db.flush()
        db.add(AssignedProblem(student_id=7, question_id=42))
        db.commit()
    try:
        yield engine
    finally:
        engine.dispose()


def test_existing_questions_and_links_survive_upgrade_and_repeated_startup(old_database):
    create_tables(old_database)
    old_database.dispose()
    create_tables(old_database)
    assert {column["name"] for column in inspect(old_database).get_columns("problems")} == {
        "id", "text", "topic", "correct_answer", "explanation"
    }
    with Session(old_database) as db:
        question = db.get(Question, 42)
        assert question.text == "What is 2 + 2?"
        assert question.correct_answer == ["4", "four"]
        assert question.explanation == "Two plus two equals four."
        assert db.get(User, 7).first_name == "Maya"
        assert db.get(AssignedProblem, (7, 42)) is not None
        db.add(Question(text="Next", topic="Math", correct_answer=["5"]))
        db.commit()
        assert len(list(db.scalars(select(Question)))) == 2
        db.delete(question)
        db.commit()
        assert db.get(AssignedProblem, (7, 42)) is None
    with old_database.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE problems SET type = 'mcq'",
        "UPDATE problems SET choices = '[\"Original choice\"]'",
    ],
)
def test_upgrade_refuses_to_discard_other_formats_or_choices(old_database, change):
    with old_database.begin() as connection:
        connection.exec_driver_sql(change)
        original = connection.exec_driver_sql("SELECT * FROM problems").all()
    with pytest.raises(ValueError, match="Convert existing"):
        create_tables(old_database)
    assert {"type", "choices"} <= {
        column["name"] for column in inspect(old_database).get_columns("problems")
    }
    with old_database.connect() as connection:
        assert connection.exec_driver_sql("SELECT * FROM problems").all() == original
        assert connection.exec_driver_sql("SELECT * FROM assigned_problems").all() == [(7, 42)]
