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


class ContentTypeConfusionTests(TestCase):
    """A declared Content-Type is untrusted input, and so is the extension.

    The old check was an OR: `ctype not allowed AND not ext_ok -> reject`. A file
    named "evil.mp4" declaring `text/html` passed on the extension alone, was
    stored verbatim, and was served back inline as text/html by lesson_video_view -
    stored XSS, and the media routes had no CSP to fall back on.
    """
    def _upload(self, filename, ctype, payload=b'<script>alert(1)</script>'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.courses.storage import DatabaseVideoStorage, UploadNotAllowed
        s = DatabaseVideoStorage()
        f = SimpleUploadedFile(filename, payload, content_type=ctype)
        try:
            return s.save(f'lesson_videos/{filename}', f), None
        except UploadNotAllowed as exc:
            return None, exc

    def test_mp4_declaring_text_html_is_rejected(self):
        name, exc = self._upload('evil.mp4', 'text/html')
        self.assertIsNone(name)
        self.assertIsNotNone(exc)

    def test_mp4_declaring_image_png_is_rejected(self):
        _, exc = self._upload('sneaky.mp4', 'image/png')
        self.assertIsNotNone(exc)

    def test_wrong_extension_with_video_type_is_rejected(self):
        _, exc = self._upload('payload.exe', 'video/mp4')
        self.assertIsNotNone(exc)

    def test_stored_type_is_re_derived_not_client_claimed(self):
        """A real .mp4 with no declared type is stored as video/mp4."""
        from apps.courses.storage import DatabaseVideoStorage
        from django.core.files.uploadedfile import SimpleUploadedFile
        s = DatabaseVideoStorage()
        f = SimpleUploadedFile('clip.mp4', b'\x00\x00\x00\x18ftypmp42', content_type='')
        name = s.save('lesson_videos/clip.mp4', f)
        self.assertEqual(s._model().objects.get(name=name).content_type, 'video/mp4')

    def test_pdf_path_rejects_html_smuggled_as_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.courses.storage import DatabaseUploadStorage, UploadNotAllowed
        s = DatabaseUploadStorage()
        f = SimpleUploadedFile('doc.pdf', b'<html>x</html>', content_type='text/html')
        with self.assertRaises(UploadNotAllowed):
            s.save('sop_pdfs/doc.pdf', f)

    def test_genuine_uploads_still_work(self):
        """The fix must not reject the two things that legitimately upload."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.courses.storage import DatabaseVideoStorage, DatabaseUploadStorage
        v = DatabaseVideoStorage()
        f = SimpleUploadedFile('ok.mp4', b'\x00\x00\x00\x18ftypmp42', content_type='video/mp4')
        self.assertTrue(v.save('lesson_videos/ok.mp4', f))
        d = DatabaseUploadStorage()
        g = SimpleUploadedFile('ok.pdf', b'%PDF-1.7\n', content_type='application/pdf')
        self.assertTrue(d.save('sop_pdfs/ok.pdf', g))
