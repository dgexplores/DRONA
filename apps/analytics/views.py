import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import StreamingHttpResponse
from django.db.models import Count, Avg, Q, Sum
from django.core.paginator import Paginator
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta

from apps.users.models import StaffUser, Department
from apps.courses.models import Course, Enrollment, LessonProgress, Lesson
from apps.quizzes.models import QuizAttempt, Quiz

# An enrolment with watch time but no activity for this long is reported as
# "fell behind". One week is long enough that a fortnightly-leave or a
# low-traffic month does not get someone flagged as a dropout.
STALE_AFTER_DAYS = 7


def _mmss(seconds):
    """Compact duration for a table cell: '9m 12s', '48s', '0s'."""
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"


def _watch_progress_rows(course):
    """Per-employee watch detail for one course.

    Shared by the report and its CSV export so the two can never disagree.
    Watch time is only meaningful for video lessons that have a duration -
    those are the grid columns. Lessons that cannot be watch-verified (PDF
    SOPs, or a video with no duration set) are summarised as a count instead
    of adding meaningless columns.
    """
    lessons = list(
        Lesson.objects.filter(module__course=course, lesson_type='video',
                              duration_minutes__gt=0)
        .select_related('module')
        .order_by('module__order', 'order')
    )
    other_total = Lesson.objects.filter(module__course=course).exclude(
        pk__in=[l.pk for l in lessons]
    ).count()

    enrollments = (
        Enrollment.objects.filter(course=course)
        .select_related('staff_user', 'staff_user__department')
        .order_by('staff_user__employee_id')
    )

    seen = {}
    for lp in LessonProgress.objects.filter(enrollment__in=enrollments):
        seen[(lp.enrollment_id, lp.lesson_id)] = lp

    rows = []
    for e in enrollments:
        cells = []
        for lesson in lessons:
            lp = seen.get((e.id, lesson.id))
            duration = (lesson.duration_minutes or 0) * 60
            watched = lp.watched_seconds if lp else 0
            cells.append({
                'lesson': lesson,
                'watched': watched,
                'watched_display': _mmss(watched),
                'duration': duration,
                'duration_display': _mmss(duration),
                # watched_seconds is clamped to the duration server-side, so
                # this ratio is always sane and never exceeds 100.
                'percent': min(100, round(watched * 100 / duration)) if duration else 0,
                'position': lp.last_position_seconds if lp else 0,
                'completed': bool(lp and lp.is_completed),
                'updated_at': lp.updated_at if lp else None,
            })

        done_other = sum(
            1 for lp in seen.values()
            if lp.enrollment_id == e.id and lp.is_completed
            and lp.lesson_id not in {l.pk for l in lessons}
        )
        total_watched = sum(c['watched'] for c in cells)
        last_activity = max(
            (c['updated_at'] for c in cells if c['updated_at']), default=None
        )
        rows.append({
            'enrollment': e,
            'cells': cells,
            'total_watched': total_watched,
            'total_watched_display': _mmss(total_watched),
            'other_completed': done_other,
            'other_total': other_total,
            'started': total_watched > 0,
            'completed': e.is_completed,
            'last_activity': last_activity,
        })

    cutoff = timezone.now() - timedelta(days=STALE_AFTER_DAYS)
    return {
        'lessons': lessons,
        'other_total': other_total,
        'rows': rows,
        'not_started': [r for r in rows if not r['started']],
        'fell_behind': [
            r for r in rows
            if r['started'] and not r['completed']
            and (r['last_activity'] is None or r['last_activity'] < cutoff)
        ],
    }


@login_required
def watch_progress_view(request):
    if not bool(getattr(request.user, 'is_manager', False)):
        return render(request, 'errors/403.html', status=403)

    # Only courses somebody is actually enrolled in - an empty report is noise.
    courses = list(
        Course.objects.filter(enrollments__isnull=False)
        .distinct().order_by('title')
    )

    course = None
    wanted = request.GET.get('course')
    if wanted:
        course = next((c for c in courses if str(c.id) == wanted), None)
        if course is None:
            messages.error(request, _("Please choose a course from the list."))
    if course is None and courses:
        course = courses[0]

    data = _watch_progress_rows(course) if course else {
        'lessons': [], 'other_total': 0, 'rows': [],
        'not_started': [], 'fell_behind': [],
    }

    return render(request, 'analytics/watch_progress.html', {
        'courses': courses,
        'course': course,
        'lessons': data['lessons'],
        'other_total': data['other_total'],
        'rows': data['rows'],
        'not_started': data['not_started'],
        'fell_behind': data['fell_behind'],
        'stale_days': STALE_AFTER_DAYS,
    })


@login_required
def export_watch_progress_csv(request):
    if not bool(getattr(request.user, 'is_manager', False)):
        return render(request, 'errors/403.html', status=403)

    courses = list(
        Course.objects.filter(enrollments__isnull=False)
        .distinct().order_by('title')
    )
    course = next((c for c in courses if str(c.id) == request.GET.get('course')), None)
    if course is None:
        course = courses[0] if courses else None
    if course is None:
        return render(request, 'errors/403.html', status=403)

    data = _watch_progress_rows(course)

    def rows():
        header = ['Employee ID', 'Name', 'Department', 'Course',
                  'Lessons Watched', 'Total Watched', 'Course Status']
        for lesson in data['lessons']:
            header += [f"{lesson.title} (watched)", f"{lesson.title} (percent)"]
        yield header
        for r in data['rows']:
            e = r['enrollment']
            watched = sum(1 for c in r['cells'] if c['watched'] > 0)
            status = "Completed" if r['completed'] else (
                "Not started" if not r['started'] else "In progress"
            )
            row = [e.staff_user.employee_id, e.staff_user.get_full_name(),
                   e.staff_user.department.name if e.staff_user.department else 'N/A',
                   course.title, watched, r['total_watched_display'], status]
            for c in r['cells']:
                row += [c['watched_display'], c['percent']]
            yield row

    class Echo:
        def write(self, value):
            return value

    writer = csv.writer(Echo())
    response = StreamingHttpResponse(
        (writer.writerow(r) for r in rows()), content_type='text/csv'
    )
    slug = course.title.lower().replace(' ', '_')[:40]
    response['Content-Disposition'] = (
        f'attachment; filename="watch_progress_{slug}.csv"'
    )
    return response


@login_required
def hr_dashboard_view(request):
    if not bool(getattr(request.user, 'is_manager', False)):
        messages.error(request, _("Access restricted to HODs and HR Administrators."))
        return redirect('dashboard')

    departments = Department.objects.all()
    dept_stats = []

    for dept in departments:
        staff_members = StaffUser.objects.filter(department=dept)
        total_staff = staff_members.count()
        enrollments = Enrollment.objects.filter(staff_user__department=dept)
        total_enrollments = enrollments.count()
        completed_enrollments = enrollments.filter(is_completed=True).count()
        completion_rate = round((completed_enrollments / total_enrollments) * 100, 1) if total_enrollments > 0 else 0

        dept_stats.append({
            'department': dept,
            'total_staff': total_staff,
            'total_enrollments': total_enrollments,
            'completed_enrollments': completed_enrollments,
            'completion_rate': completion_rate,
        })

    total_staff_count = StaffUser.objects.count()
    total_courses_count = Course.objects.count()
    from apps.certificates.models import Certificate as _Cert
    total_cert_count = _Cert.objects.count()
    total_completed_enrollments = Enrollment.objects.filter(is_completed=True).count()
    avg_quiz_score = QuizAttempt.objects.aggregate(Avg('score'))['score__avg'] or 0.0
    total_learning_hours = (Enrollment.objects.aggregate(Sum('watch_seconds'))['watch_seconds__sum'] or 0) / 3600

    recent_attempts = QuizAttempt.objects.select_related('staff_user', 'quiz').order_by('-attempted_at')[:10]

    is_admin = request.user.role in ('admin', 'hod') or request.user.is_superuser
    pending_qs = StaffUser.objects.filter(is_active=False).select_related('department').order_by('date_joined') if is_admin else StaffUser.objects.none()
    paginator = Paginator(pending_qs, 20)
    pending_page = paginator.get_page(request.GET.get('pending_page'))
    pending_users = pending_page

    context = {
        'dept_stats': dept_stats,
        'total_staff_count': total_staff_count,
        'total_courses_count': total_courses_count,
        'total_cert_count': total_cert_count,
        'total_completed_enrollments': total_completed_enrollments,
        'avg_quiz_score': round(avg_quiz_score, 1),
        'total_learning_hours': round(total_learning_hours, 1),
        'recent_attempts': recent_attempts,
        'pending_users': pending_users,
        'pending_page': pending_page,
        'is_admin': is_admin,
    }
    return render(request, 'analytics/hr_dashboard.html', context)

@login_required
def export_staff_report_csv(request):
    if not bool(getattr(request.user, 'is_manager', False)):
        return render(request, 'errors/403.html', status=403)

    # Streaming + annotated counts: avoids loading all rows and N+1 per-row counts.
    qs = (StaffUser.objects.select_related('department')
          .annotate(
              total_e=Count('enrollments', distinct=True),
              completed_e=Count('enrollments', filter=Q(enrollments__is_completed=True), distinct=True),
              cert_n=Count('certificates', distinct=True),
          )
          .order_by('employee_id')
          .iterator(chunk_size=500))

    def rows():
        yield ['Employee ID', 'Name', 'Department', 'Role', 'Enrolled Courses', 'Completed Courses', 'Certificates Earned']
        for staff in qs:
            yield [
                staff.employee_id,
                staff.get_full_name(),
                staff.department.name if staff.department else 'N/A',
                staff.get_role_display(),
                staff.total_e,
                staff.completed_e,
                staff.cert_n,
            ]

    class Echo:
        def write(self, value):
            return value

    writer = csv.writer(Echo())
    response = StreamingHttpResponse((writer.writerow(r) for r in rows()), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="srms_dorna_staff_report.csv"'
    return response
