from app.models import Role
from app.schemas import UserPublic


class PermissionDenied(Exception):
    pass


def require_teacher(user: UserPublic) -> None:
    if user.role != Role.TEACHER:
        raise PermissionDenied("Teacher role required")


def require_student(user: UserPublic) -> None:
    if user.role != Role.STUDENT:
        raise PermissionDenied("Student role required")
