"""Uploaded lesson videos must be seekable.

A <video> element requests byte ranges; if the server replies 200 instead of 206
the browser either cannot seek or refuses to play at all. These pin the range
contract, plus the enrollment gate.
"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, RequestFactory

from apps.courses.models import Category, Course, Enrollment, Lesson, Module, StoredUpload
from apps.users.models import Department, StaffUser

MP4 = b'\x00\x00\x00\x20ftypmp42' + b'x' * 5000


def build():
    cat, _ = Category.objects.get_or_create(name="Safety", defaults={"name_hi": "सुरक्षा"})
    course = Course.objects.create(title="C", description="d", category=cat)
    module = Module.objects.create(course=course, title="M", order=1)
    lesson = Lesson.objects.create(
        module=module, title="V", lesson_type="video", order=1,
        video_file=SimpleUploadedFile("clip.mp4", MP4, content_type="video/mp4"),
    )
    return course, lesson


class VideoServingTests(TestCase):
    def setUp(self):
        self.course, self.lesson = build()
        self.dept = Department.objects.create(name="IT", code="IT")
        self.staff = StaffUser.objects.create_user(
            employee_id="EMPV1", username="empv1", email="e1@srms.ac.in",
            password="pass12345", role="staff", department=self.dept)
        self.other = StaffUser.objects.create_user(
            employee_id="EMPV2", username="empv2", email="e2@srms.ac.in",
            password="pass12345", role="staff", department=self.dept)
        Enrollment.objects.create(staff_user=self.staff, course=self.course)
        self.url = f"/videos/{self.lesson.id}/"

    def test_enrolled_staff_gets_the_whole_file_and_range_support(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Accept-Ranges"], "bytes")
        self.assertEqual(int(r["Content-Length"]), len(MP4))
        self.assertEqual(r["Content-Type"], "video/mp4")
        self.assertEqual(b"".join(r.streaming_content), MP4)

    def test_unenrolled_staff_is_refused(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_mid_file_range_returns_206_with_the_right_slice(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.url, HTTP_RANGE="bytes=100-199")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Range"], f"bytes 100-199/{len(MP4)}")
        self.assertEqual(int(r["Content-Length"]), 100)
        self.assertEqual(b"".join(r.streaming_content), MP4[100:200])

    def test_open_ended_range_runs_to_the_end(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.url, HTTP_RANGE=f"bytes={len(MP4) - 10}-")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(b"".join(r.streaming_content), MP4[-10:])

    def test_suffix_range_returns_the_tail(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.url, HTTP_RANGE="bytes=-20")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(b"".join(r.streaming_content), MP4[-20:])

    def test_range_past_the_end_is_416(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.url, HTTP_RANGE=f"bytes={len(MP4) + 10}-{len(MP4) + 20}")
        self.assertEqual(r.status_code, 416)
        self.assertEqual(r["Content-Range"], f"bytes */{len(MP4)}")

    def test_bytes_are_actually_in_the_database(self):
        row = StoredUpload.objects.get(name=self.lesson.video_file.name)
        self.assertEqual(bytes(row.content), MP4)
        self.assertEqual(row.content_type, "video/mp4")
