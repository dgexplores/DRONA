from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db import transaction
from django.db.models import F
import json
import logging
import os
import re
from datetime import datetime as dt, timedelta as td

from apps.courses.models import (Course, Category, Module, Lesson, Enrollment, LessonProgress,
                               TrainingSession, StoredUpload)
from apps.courses.video import resolve_video
from apps.users.models import Department, StaffUser
from apps.certificates.models import Certificate

logger = logging.getLogger(__name__)


def _as_int(value, default=0):
    """Coerce untrusted JSON input to int without raising."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@login_required
def dashboard_view(request):
    user = request.user

    # Managers (super admin / HOD) get a command-center dashboard,
    # not the learner catalogue. Return before any learner auto-enrollment.
    is_manager = bool(getattr(user, 'is_manager', False))
    if is_manager:
        return _manager_dashboard(request)

    # Auto-enroll in mandatory courses for user's department
    if user.department:
        mandatory_courses = Course.objects.filter(is_mandatory=True, target_departments=user.department)
        for course in mandatory_courses:
            Enrollment.objects.get_or_create(staff_user=user, course=course)

    user_enrollments = Enrollment.objects.filter(staff_user=user).select_related('course')
    enrolled_course_ids = user_enrollments.values_list('course_id', flat=True)

    # Self-service catalog: elective courses not yet enrolled (mandatory is assigned by admin/HOD).
    available_courses = Course.objects.filter(is_mandatory=False).exclude(id__in=enrolled_course_ids)

    # Metrics
    completed_count = user_enrollments.filter(is_completed=True).count()
    in_progress_count = user_enrollments.filter(is_completed=False).count()
    certificates_count = user.certificates.count()

    context = {
        'user_enrollments': user_enrollments,
        'available_courses': available_courses,
        'completed_count': completed_count,
        'in_progress_count': in_progress_count,
        'certificates_count': certificates_count,
    }
    return render(request, 'courses/dashboard.html', context)


def _manager_dashboard(request):
    """Role-aware home page for super-admin and HOD accounts.

    Super admin sees platform-wide numbers; HODs see department-level
    numbers for their own department. Both get shortcuts to the management
    console, HR analytics, certificate directory, and pending approvals.
    """
    user = request.user
    is_super = user.is_superuser or user.role == 'admin'

    dept = user.department

    def staff_qs():
        qs = StaffUser.objects.filter(is_active=True)
        return qs if is_super or not dept else qs.filter(department=dept)

    def enrollment_qs():
        qs = Enrollment.objects.all()
        return qs if is_super or not dept else qs.filter(staff_user__department=dept)

    staff_members = staff_qs()
    enrollments = enrollment_qs()

    active_staff = staff_members.count()
    completed = enrollments.filter(is_completed=True).count()
    total_courses = Course.objects.count()
    course_count = enrollments.count()
    certificates_count = Certificate.objects.count() if is_super else Certificate.objects.filter(staff_user__department=dept).count()
    pending_count = StaffUser.objects.filter(is_active=False).count()
    sessions_this_month = TrainingSession.objects.filter(date__year=timezone.localdate().year, date__month=timezone.localdate().month).count()

    scope_label = "all departments" if is_super else (dept.name if dept else "your department")

    recent_enrollments = enrollments.select_related('staff_user', 'course').order_by('-enrolled_at')[:8]

    context = {
        'is_super': is_super,
        'active_staff': active_staff,
        'completed_count': completed,
        'course_count': total_courses,
        'enrollment_count': course_count,
        'pending_count': pending_count,
        'certificates_count': certificates_count,
        'sessions_this_month': sessions_this_month,
        'scope_label': scope_label,
        'recent_enrollments': recent_enrollments,
    }
    return render(request, 'courses/manager_dashboard.html', context)

@login_required
def course_detail_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    # Managers may preview any course; staff may view assigned courses or self-enroll into electives.
    is_manager = bool(getattr(request.user, 'is_manager', False))

    try:
        enrollment = Enrollment.objects.get(staff_user=request.user, course=course)
    except Enrollment.DoesNotExist:
        if is_manager:
            enrollment = None
        elif not course.is_mandatory:
            # Self-service enrollment for elective courses.
            enrollment, _ = Enrollment.objects.get_or_create(staff_user=request.user, course=course)
            messages.success(request, f"You are now enrolled in '{course.title}'.")
        else:
            messages.error(request, "This course has not been assigned to you yet.")
            return redirect('dashboard')

    modules = course.modules.prefetch_related('lessons').all()

    # Fetch lesson progress for current enrollment
    progress_map = {}
    if enrollment is not None:
        progress_map = {
            lp.lesson_id: lp
            for lp in LessonProgress.objects.filter(enrollment=enrollment)
        }

    # Quiz status
    quiz_attempts = request.user.quiz_attempts.filter(quiz__course=course).order_by('-attempted_at')
    latest_attempt = quiz_attempts.first()

    context = {
        'course': course,
        'enrollment': enrollment,
        'modules': modules,
        'progress_map': progress_map,
        'latest_attempt': latest_attempt,
    }
    return render(request, 'courses/course_detail.html', context)

@login_required
def lesson_view(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course = lesson.module.course

    is_manager = bool(getattr(request.user, 'is_manager', False))
    try:
        enrollment = Enrollment.objects.get(staff_user=request.user, course=course)
    except Enrollment.DoesNotExist:
        if is_manager:
            enrollment = None
        elif not course.is_mandatory:
            enrollment, _ = Enrollment.objects.get_or_create(staff_user=request.user, course=course)
        else:
            messages.error(request, "This course has not been assigned to you yet.")
            return redirect('dashboard')

    progress = None
    if enrollment is not None:
        progress, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)

    # Next / Prev lesson navigation
    all_lessons = list(Lesson.objects.filter(module__course=course).order_by('module__order', 'order'))
    curr_idx = all_lessons.index(lesson)
    prev_lesson = all_lessons[curr_idx - 1] if curr_idx > 0 else None
    next_lesson = all_lessons[curr_idx + 1] if curr_idx < len(all_lessons) - 1 else None

    context = {
        'lesson': lesson,
        'course': course,
        'enrollment': enrollment,
        'progress': progress,
        'prev_lesson': prev_lesson,
        'next_lesson': next_lesson,
        # A pasted YouTube/Vimeo link cannot be played by <video src>, so tell the
        # template which kind of player to render.
        'video': resolve_video(lesson.video_url),
    }
    return render(request, 'courses/lesson.html', context)

@login_required
def sop_document_view(request, lesson_id):
    """Permission-checked SOP PDF serve. Enrolled staff or managers only.

    Replaces direct /media/ links for SOPs. Direct media remains login-gated
    as defense-in-depth; this view enforces enrollment-level auth.
    """
    from django.http import FileResponse, Http404
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course = lesson.module.course
    is_manager = bool(getattr(request.user, 'is_manager', False))
    if not is_manager:
        if not Enrollment.objects.filter(staff_user=request.user, course=course).exists():
            raise Http404("Not enrolled in this course.")
    if not lesson.pdf_file:
        raise Http404("No SOP document for this lesson.")
    try:
        handle = lesson.pdf_file.open('rb')
    except (FileNotFoundError, OSError, StoredUpload.DoesNotExist):
        # The filesystem backend raised FileNotFoundError; the database backend
        # raises DoesNotExist. Both mean "the bytes are gone".
        raise Http404("SOP file not found.")
    response = FileResponse(handle, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{os.path.basename(lesson.pdf_file.name)}"'
    response['Content-Length'] = lesson.pdf_file.size
    return response


@login_required
def save_lesson_progress(request, lesson_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'invalid method'}, status=405)
    try:
        data = json.loads(request.body)
        lesson = get_object_or_404(Lesson, id=lesson_id)
        # Only enrolled staff may record progress.
        try:
            enrollment = Enrollment.objects.get(staff_user=request.user, course=lesson.module.course)
        except Enrollment.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Not enrolled in this course.'}, status=403)

        # Bound position: 0 .. lesson duration. Prevents negative / huge spoofing.
        position = _as_int(data.get('position', 0))
        max_position = max(0, (lesson.duration_minutes or 0) * 60)
        position = max(0, min(position, max_position))

        progress, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)
        progress.last_position_seconds = position

        if progress.requires_watch_time:
            # Completion is derived from server-accumulated watch time only.
            # The client-supplied `completed` flag is deliberately ignored here
            # so a hand-crafted request cannot mint a certificate.
            credited = progress.register_watch(data.get('watched', 0))
            if credited:
                Enrollment.objects.filter(pk=enrollment.pk).update(
                    watch_seconds=F('watch_seconds') + credited
                )
        elif data.get('completed'):
            # PDF lessons and lessons with no duration cannot be verified by
            # watch time; an explicit acknowledgement is the honest floor.
            progress.acknowledge()

        progress.save()

        with transaction.atomic():
            enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
            enrollment.update_progress()

        return JsonResponse({
            'status': 'success',
            'progress_percent': enrollment.progress_percent,
            'lesson_completed': progress.is_completed,
        })
    except Exception:
        logger.exception("Failed to save progress for lesson %s", lesson_id)
        return JsonResponse({'status': 'error', 'message': 'Could not save progress.'}, status=400)


@login_required
def training_calendar(request):
    month = request.GET.get('month') or timezone.localdate().strftime('%Y-%m')
    try:
        year, month_num = [int(p) for p in month.split('-')]
        if not 1 <= month_num <= 12:
            raise ValueError("month out of range")
    except (ValueError, AttributeError):
        year, month_num = timezone.localdate().year, timezone.localdate().month

    sessions = TrainingSession.objects.filter(date__year=year, date__month=month_num)

    # Group sessions by day for the calendar grid.
    day_map = {}
    for s in sessions:
        day_map.setdefault(s.date.day, []).append(s)

    is_manager = request.user.role in ('hod', 'admin') or request.user.is_superuser or request.user.is_staff

    context = {
        'sessions': sessions,
        'day_map': day_map,
        'year': year,
        'month': month_num,
        'current_month': month,
        'month_name': dt(year, month_num, 1).strftime('%B'),
        'prev': (dt(year, month_num, 1) - td(days=1)).strftime('%Y-%m'),
        'next': f"{year}-{month_num + 1:02d}" if month_num < 12 else f"{year + 1}-01",
        'is_manager': is_manager,
    }
    return render(request, 'courses/training_calendar.html', context)


@login_required
@require_POST
def enroll_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if course.is_mandatory:
        messages.error(request, "Mandatory courses are assigned by your HOD and cannot be self-enrolled.")
        return redirect('course_detail', course_id=course.id)

    _, created = Enrollment.objects.get_or_create(staff_user=request.user, course=course)
    if created:
        messages.success(request, f"You are now enrolled in '{course.title}'.")
    else:
        messages.info(request, f"You are already enrolled in '{course.title}'.")
    return redirect('course_detail', course_id=course.id)


def _range_response(request, data, content_type, filename):
    """Serve stored bytes with HTTP Range support.

    A <video> element asks for byte ranges to seek, and several browsers refuse
    to play at all if the server ignores the header and replies 200. Slicing the
    bytes here is what makes scrubbing work.
    """
    from django.http import StreamingHttpResponse
    import mimetypes

    total = len(data)
    range_header = request.headers.get('Range', '')
    ctype = content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    filename = os.path.basename(filename)

    start, end = 0, total - 1
    partial = False
    m = re.match(r'bytes=(\d*)-(\d*)$', range_header.strip()) if range_header else None
    if m:
        g1, g2 = m.group(1), m.group(2)
        if g1:
            start = int(g1)
            end = int(g2) if g2 else total - 1
        elif g2:
            # suffix range: last N bytes
            start = max(0, total - int(g2))
        if start >= total or start > end:
            r = HttpResponse(status=416)
            r['Content-Range'] = f'bytes */{total}'
            return r
        end = min(end, total - 1)
        partial = True

    length = end - start + 1
    chunk_size = 256 * 1024

    def stream():
        for offset in range(start, end + 1, chunk_size):
            yield bytes(data[offset:min(offset + chunk_size, end + 1)])

    response = StreamingHttpResponse(stream(), status=206 if partial else 200,
                                     content_type=ctype)
    response['Content-Length'] = str(length)
    response['Accept-Ranges'] = 'bytes'
    if partial:
        response['Content-Range'] = f'bytes {start}-{end}/{total}'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
def lesson_video_view(request, lesson_id):
    """Serve an uploaded lesson video, gated on enrollment like every other asset."""
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if not lesson.video_file:
        raise Http404("No uploaded video for this lesson.")
    is_manager = bool(getattr(request.user, 'is_manager', False))
    if not is_manager and not Enrollment.objects.filter(
        staff_user=request.user, course=lesson.module.course
    ).exists():
        raise Http404("Not found.")
    row = StoredUpload.objects.filter(name=lesson.video_file.name).first()
    if row is None:
        raise Http404("Video file not found.")
    return _range_response(request, bytes(row.content), row.content_type, row.name)
