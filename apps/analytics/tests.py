from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.users.models import Department
from apps.courses.models import Category, Course
from apps.quizzes.models import Quiz, Question, Choice, QuizAttempt

StaffUser = get_user_model()


class AnalyticsAccessTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="IT", code="IT")
        self.cat = Category.objects.create(name="Safety")
        self.course = Course.objects.create(title="Safety", category=self.cat)
        self.staff = StaffUser.objects.create_user(
            employee_id="EMP500", username="emp500", email="a@b.com",
            password="pass12345", role="staff", department=self.dept
        )
        self.hod = StaffUser.objects.create_user(
            employee_id="EMP501", username="emp501", email="c@d.com",
            password="pass12345", role="hod", department=self.dept
        )

    def test_staff_denied_hr_dashboard(self):
        self.client.login(employee_id='EMP500', password='pass12345')
        resp = self.client.get(reverse('hr_dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_hod_allowed_hr_dashboard(self):
        self.client.login(employee_id='EMP501', password='pass12345')
        resp = self.client.get(reverse('hr_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('dept_stats', resp.context)

    def test_staff_denied_csv(self):
        self.client.login(employee_id='EMP500', password='pass12345')
        resp = self.client.get(reverse('export_staff_csv'))
        self.assertEqual(resp.status_code, 403)
        self.assertTemplateUsed(resp, 'errors/403.html')

    def test_hod_csv_export(self):
        self.client.login(employee_id='EMP501', password='pass12345')
        resp = self.client.get(reverse('export_staff_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        content = b''.join(resp.streaming_content)
        self.assertTrue(content.startswith(b'Employee ID'))


class WatchProgressReportTests(TestCase):
    """The report reads watch time that already exists; these cover the
    gating, the arithmetic, and the two roll-ups HR actually acts on."""

    def setUp(self):
        from apps.courses.models import Enrollment, Lesson, LessonProgress, Module
        self.M = (Enrollment, Lesson, LessonProgress, Module)
        self.dept = Department.objects.create(name="IT", code="IT")
        self.cat = Category.objects.create(name="Safety")
        self.course = Course.objects.create(title="Safety", category=self.cat)
        self.module = Module.objects.create(course=self.course, title="M1", order=1)
        # duration 10 min = 600s, so percentages are easy to reason about
        self.lesson = Lesson.objects.create(
            module=self.module, title="L1", lesson_type="video", duration_minutes=10
        )
        # a PDF cannot be watch-verified, so it must not become a grid column
        self.pdf = Lesson.objects.create(
            module=self.module, title="P1", lesson_type="pdf"
        )
        self.staff = StaffUser.objects.create_user(
            employee_id="EMP600", username="emp600", email="e@f.com",
            password="pass12345", role="staff", department=self.dept
        )
        self.hod = StaffUser.objects.create_user(
            employee_id="EMP601", username="emp601", email="g@h.com",
            password="pass12345", role="hod", department=self.dept
        )
        self.enr = Enrollment.objects.create(staff_user=self.staff, course=self.course)

    def test_staff_denied(self):
        self.client.login(employee_id='EMP600', password='pass12345')
        resp = self.client.get(reverse('watch_progress'))
        self.assertEqual(resp.status_code, 403)
        self.assertTemplateUsed(resp, 'errors/403.html')

    def test_staff_denied_csv(self):
        self.client.login(employee_id='EMP600', password='pass12345')
        self.assertEqual(self.client.get(reverse('export_watch_progress_csv')).status_code, 403)

    def test_hod_sees_report(self):
        self.client.login(employee_id='EMP601', password='pass12345')
        resp = self.client.get(reverse('watch_progress'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['rows']), 1)
        self.assertEqual(resp.context['course'], self.course)

    def test_pdf_is_not_a_grid_column(self):
        self.client.login(employee_id='EMP601', password='pass12345')
        resp = self.client.get(reverse('watch_progress'))
        self.assertEqual([l.pk for l in resp.context['lessons']], [self.lesson.pk])
        self.assertEqual(resp.context['other_total'], 1)

    def test_watched_seconds_become_a_percent(self):
        Enrollment, Lesson, LessonProgress, Module = self.M
        LessonProgress.objects.create(
            enrollment=self.enr, lesson=self.lesson, watched_seconds=300
        )
        self.client.login(employee_id='EMP601', password='pass12345')
        row = self.client.get(reverse('watch_progress')).context['rows'][0]
        self.assertEqual(row['cells'][0]['percent'], 50)
        self.assertEqual(row['cells'][0]['watched_display'], '5m 00s')
        self.assertTrue(row['started'])
        self.assertEqual(row['total_watched_display'], '5m 00s')

    def test_zero_watch_counts_as_not_started(self):
        self.client.login(employee_id='EMP601', password='pass12345')
        ctx = self.client.get(reverse('watch_progress')).context
        self.assertEqual(len(ctx['not_started']), 1)
        self.assertEqual(ctx['fell_behind'], [])

    def test_a_progress_row_recording_is_neither_flag(self):
        """Started-but-not-finished with fresh activity is healthy, not a dropout."""
        from django.utils import timezone
        Enrollment, Lesson, LessonProgress, Module = self.M
        lp = LessonProgress.objects.create(
            enrollment=self.enr, lesson=self.lesson, watched_seconds=60
        )
        lp.updated_at = timezone.now()
        lp.save()
        self.client.login(employee_id='EMP601', password='pass12345')
        ctx = self.client.get(reverse('watch_progress')).context
        self.assertEqual(ctx['not_started'], [])
        self.assertEqual(ctx['fell_behind'], [])

    def test_stale_partial_watch_is_fell_behind(self):
        from django.utils import timezone
        from datetime import timedelta
        Enrollment, Lesson, LessonProgress, Module = self.M
        lp = LessonProgress.objects.create(
            enrollment=self.enr, lesson=self.lesson, watched_seconds=60
        )
        LessonProgress.objects.filter(pk=lp.pk).update(
            updated_at=timezone.now() - timedelta(days=30)
        )
        self.client.login(employee_id='EMP601', password='pass12345')
        ctx = self.client.get(reverse('watch_progress')).context
        self.assertEqual(len(ctx['fell_behind']), 1)
        self.assertEqual(ctx['not_started'], [])

    def test_finished_staff_are_not_flagged_as_fell_behind(self):
        from django.utils import timezone
        from datetime import timedelta
        Enrollment, Lesson, LessonProgress, Module = self.M
        lp = LessonProgress.objects.create(
            enrollment=self.enr, lesson=self.lesson, watched_seconds=600, is_completed=True
        )
        LessonProgress.objects.filter(pk=lp.pk).update(
            updated_at=timezone.now() - timedelta(days=30)
        )
        self.enr.is_completed = True
        self.enr.save()
        self.client.login(employee_id='EMP601', password='pass12345')
        ctx = self.client.get(reverse('watch_progress')).context
        self.assertEqual(ctx['fell_behind'], [])
        self.assertTrue(ctx['rows'][0]['completed'])

    def test_percent_cannot_exceed_100(self):
        """watched_seconds is clamped server-side, but the report must not
        rely on that alone if a row is ever written another way."""
        Enrollment, Lesson, LessonProgress, Module = self.M
        LessonProgress.objects.create(
            enrollment=self.enr, lesson=self.lesson, watched_seconds=99999
        )
        self.client.login(employee_id='EMP601', password='pass12345')
        row = self.client.get(reverse('watch_progress')).context['rows'][0]
        self.assertLessEqual(row['cells'][0]['percent'], 100)

    def test_csv_has_a_column_per_lesson(self):
        self.client.login(employee_id='EMP601', password='pass12345')
        resp = self.client.get(
            reverse('export_watch_progress_csv'), {'course': self.course.id}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn('watch_progress_safety.csv', resp['Content-Disposition'])
        body = b''.join(resp.streaming_content).decode()
        header = body.splitlines()[0].split(',')
        self.assertIn('L1 (watched)', header)
        self.assertIn('L1 (percent)', header)
        self.assertNotIn('P1 (watched)', header)
        self.assertIn('EMP600', body)

    def test_course_with_no_enrollments_is_not_offered(self):
        empty = Course.objects.create(title="Empty", category=self.cat)
        self.client.login(employee_id='EMP601', password='pass12345')
        resp = self.client.get(reverse('watch_progress'))
        self.assertNotIn(empty, resp.context['courses'])

    def test_unknown_course_id_is_rejected(self):
        self.client.login(employee_id='EMP601', password='pass12345')
        resp = self.client.get(reverse('watch_progress'), {'course': '999999'})
        self.assertEqual(resp.status_code, 200)
        # falls back to a real course rather than erroring or blanking
        self.assertEqual(resp.context['course'], self.course)

    def test_default_course_is_the_most_populated_one(self):
        """Alphabetical order used to land on a course nobody had started."""
        from apps.courses.models import Enrollment, Lesson, LessonProgress, Module
        big = Course.objects.create(title="Aaa Busy", category=self.cat)
        bm = Module.objects.create(course=big, title="M", order=1)
        bl = Lesson.objects.create(module=bm, title="L", lesson_type="video", duration_minutes=10)
        other = StaffUser.objects.create_user(
            employee_id="EMP602", username="emp602", email="i@j.com",
            password="pass12345", role="staff", department=self.dept
        )
        Enrollment.objects.create(staff_user=other, course=big)
        self.client.login(employee_id='EMP601', password='pass12345')
        self.assertEqual(self.client.get(reverse('watch_progress')).context['course'], big)

    def test_course_selector_is_ordered_by_enrollment_count(self):
        from apps.courses.models import Enrollment
        big = Course.objects.create(title="Zzz Busy", category=self.cat)
        # "Safety" already has 1 enrolment from setUp; give this one 2 so the
        # count must decide the order, not the title.
        for n in (602, 603):
            u = StaffUser.objects.create_user(
                employee_id=f"EMP{n}", username=f"emp{n}", email=f"{n}@l.com",
                password="pass12345", role="staff", department=self.dept
            )
            Enrollment.objects.create(staff_user=u, course=big)
        self.client.login(employee_id='EMP601', password='pass12345')
        self.assertEqual(self.client.get(reverse('watch_progress')).context['courses'][0], big)
