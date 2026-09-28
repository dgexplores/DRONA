"""Shared access checks for course content.

The "manager, or enrolled in this course" rule was written out three times with
drifting failure behaviour. The rule itself is centralised here; each caller
keeps its own response to a denial, because they are not the same:

* `take_quiz_view` / `submit_quiz_view` flash a message and bounce to dashboard
* `lesson_video_view` raises 404, so a probe cannot tell "not yours" from "gone"

Only the predicate is shared. Do not move the failure handling in here.
"""

from apps.courses.models import Enrollment


def can_view_course(user, course):
    """True if ``user`` is allowed to view the non-management content of ``course``.

    Managers may preview any course. Everyone else must be enrolled. A falsy
    ``course`` is treated as "nothing to gate" so callers with an optional
    course (a quiz whose course may be unset) keep working unchanged.
    """
    if course is None:
        return True
    if user.is_manager:
        return True
    return Enrollment.objects.filter(
        staff_user=user, course=course
    ).exists()
