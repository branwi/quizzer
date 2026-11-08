from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AssignedProblem, Question, Role, User
from app.schemas import AssignmentCreate, AssignmentResult
from app.services.errors import InvalidInput, ResourceNotFound


def student(db: Session, student_id: int) -> User:
    user = db.get(User, student_id)
    if user is None or user.role != Role.STUDENT:
        raise ResourceNotFound("Student not found")
    return user


def list_assigned(db: Session, student_id: int) -> list[Question]:
    student(db, student_id)
    return list(
        db.scalars(
            select(Question)
            .join(AssignedProblem, AssignedProblem.question_id == Question.id)
            .where(AssignedProblem.student_id == student_id)
            .order_by(Question.id)
        )
    )


def assign(db: Session, data: AssignmentCreate) -> AssignmentResult:
    student_ids, question_ids = set(data.student_ids), set(data.question_ids)
    found_students = set(
        db.scalars(select(User.id).where(User.id.in_(student_ids), User.role == Role.STUDENT))
    )
    found_questions = set(db.scalars(select(Question.id).where(Question.id.in_(question_ids))))
    if found_students != student_ids or found_questions != question_ids:
        raise InvalidInput("All student ids and question ids must exist")
    existing = set(
        db.execute(
            select(AssignedProblem.student_id, AssignedProblem.question_id).where(
                AssignedProblem.student_id.in_(student_ids),
                AssignedProblem.question_id.in_(question_ids),
            )
        ).all()
    )
    for student_id in student_ids:
        for question_id in question_ids:
            if (student_id, question_id) not in existing:
                db.add(AssignedProblem(student_id=student_id, question_id=question_id))
    db.commit()
    return AssignmentResult(student_ids=sorted(student_ids), question_ids=sorted(question_ids))


def unassign(db: Session, student_id: int, question_id: int) -> None:
    student(db, student_id)
    db.execute(
        delete(AssignedProblem).where(
            AssignedProblem.student_id == student_id, AssignedProblem.question_id == question_id
        )
    )
    db.commit()
