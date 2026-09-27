"""Uploaded files must outlive the process that received them.

The reason this storage exists: the app runs on a plan with no persistent disk,
so a file on the container filesystem is destroyed by the next deploy. These
tests pin the property that matters - the bytes live in the database, so nothing
about a restart can lose them.
"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.courses.models import Lesson, Module, Course, Category, StoredUpload
from apps.courses.storage import MAX_UPLOAD_BYTES, UploadTooLarge, UploadNotAllowed

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"


def make_course():
    cat, _ = Category.objects.get_or_create(name="Safety", defaults={"name_hi": "सुरक्षा"})
    return Course.objects.create(title="C", description="d", category=cat)


class DatabaseUploadStorageTests(TestCase):
    def _lesson(self, course, pdf):
        module = Module.objects.create(course=course, title="M", order=1)
        return Lesson.objects.create(module=module, title="L", lesson_type="pdf",
                                     order=1, pdf_file=pdf)

    def test_upload_is_written_to_the_database(self):
        course = make_course()
        lesson = self._lesson(course, SimpleUploadedFile("sop.pdf", PDF_BYTES,
                                                         content_type="application/pdf"))
        self.assertTrue(lesson.pdf_file.name)
        row = StoredUpload.objects.get(name=lesson.pdf_file.name)
        self.assertEqual(bytes(row.content), PDF_BYTES)
        self.assertEqual(row.size, len(PDF_BYTES))

    def test_bytes_survive_a_fresh_read(self):
        """Nothing filesystem-shaped is involved, so nothing can be swept away."""
        course = make_course()
        lesson = self._lesson(course, SimpleUploadedFile("sop.pdf", PDF_BYTES,
                                                         content_type="application/pdf"))
        reloaded = Lesson.objects.get(pk=lesson.pk)
        self.assertEqual(reloaded.pdf_file.read(), PDF_BYTES)

    def test_repeated_opens_are_stable(self):
        """Each fresh open returns the whole file, not a spent one."""
        course = make_course()
        lesson = self._lesson(course, SimpleUploadedFile("sop.pdf", PDF_BYTES,
                                                         content_type="application/pdf"))
        for _ in range(3):
            with lesson.pdf_file.storage.open(lesson.pdf_file.name) as fh:
                self.assertEqual(fh.read(), PDF_BYTES)

    def test_delete_removes_the_bytes(self):
        course = make_course()
        lesson = self._lesson(course, SimpleUploadedFile("sop.pdf", PDF_BYTES,
                                                         content_type="application/pdf"))
        name = lesson.pdf_file.name
        lesson.pdf_file.delete(save=False)
        self.assertFalse(StoredUpload.objects.filter(name=name).exists())

    def test_oversized_upload_is_refused(self):
        big = b"%PDF-1.7" + b"0" * (MAX_UPLOAD_BYTES + 10)
        with self.assertRaises(UploadTooLarge):
            self._lesson(make_course(), SimpleUploadedFile("big.pdf", big,
                                                          content_type="application/pdf"))

    def test_empty_upload_is_refused(self):
        with self.assertRaises(UploadNotAllowed):
            Lesson.objects.create(
                module=Module.objects.create(course=make_course(), title="M", order=1),
                title="L", lesson_type="pdf", order=1,
                pdf_file=SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf"),
            )

    def test_form_rejects_a_non_pdf_before_it_is_stored(self):
        """The form is the friendly gate; the storage is the hard backstop."""
        from apps.management.forms import LessonForm
        course = make_course()
        module = Module.objects.create(course=course, title="M", order=1)
        lesson = Lesson(module=module, title="L", lesson_type="pdf", order=1)
        form = LessonForm(
            {"title": "L", "lesson_type": "pdf", "duration_minutes": 5, "order": 1},
            {"pdf_file": SimpleUploadedFile("evil.exe", b"MZ",
                                            content_type="application/x-msdownload")},
            instance=lesson,
        )
        self.assertIn("pdf_file", form.errors)
        self.assertFalse(StoredUpload.objects.exists())

    def test_form_rejects_an_oversized_pdf(self):
        from apps.management.forms import LessonForm
        course = make_course()
        module = Module.objects.create(course=course, title="M", order=1)
        lesson = Lesson(module=module, title="L", lesson_type="pdf", order=1)
        big = b"%PDF-1.7" + b"0" * (MAX_UPLOAD_BYTES + 10)
        form = LessonForm(
            {"title": "L", "lesson_type": "pdf", "duration_minutes": 5, "order": 1},
            {"pdf_file": SimpleUploadedFile("big.pdf", big, content_type="application/pdf")},
            instance=lesson,
        )
        self.assertIn("pdf_file", form.errors)
        self.assertFalse(StoredUpload.objects.exists())


class StorageUrlTests(TestCase):
    def test_url_points_at_the_permission_checked_media_route(self):
        """The widget's "Currently" link must hit /media/, which runs the
        enrollment check - not a bare /uploads/ path that would 404."""
        from apps.courses.storage import DatabaseUploadStorage
        url = DatabaseUploadStorage().url("sop_documents/x.pdf")
        self.assertEqual(url, "/media/sop_documents/x.pdf")
