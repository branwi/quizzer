from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Question, Role
from app.schemas import BankFilters, BankPage, StudentBankPage, TeacherBankPage, UserPublic
from app.services.questions import for_student, for_teacher


def search(db: Session, user: UserPublic, filters: BankFilters) -> BankPage:
    conditions = [Question.is_public.is_(True)]
    if filters.q:
        conditions.append(
            or_(
                Question.text.icontains(filters.q, autoescape=True),
                Question.topic.icontains(filters.q, autoescape=True),
            )
        )
    if filters.topic:
        conditions.append(Question.topic == filters.topic)
    if filters.type is not None:
        conditions.append(Question.type == filters.type)
    total = db.scalar(select(func.count()).select_from(Question).where(*conditions))
    rows = db.scalars(
        select(Question)
        .where(*conditions)
        .order_by(Question.created_at.desc(), Question.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()
    if user.role == Role.TEACHER:
        return TeacherBankPage(
            items=[for_teacher(q) for q in rows],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )
    return StudentBankPage(
        items=[for_student(q) for q in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )
