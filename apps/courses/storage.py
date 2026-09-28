"""Durable storage for uploaded files, backed by the database.

Why this exists
---------------
The app runs on a free Render plan, which has no persistent disk: `media/` lives
on the container's ephemeral filesystem, so every uploaded file is destroyed the
next time the service restarts or deploys. Render only offers persistent disks on
paid tiers, and object storage would need an external account.

The Postgres instance is already durable, so small uploads are stored in it. That
makes SOP documents survive a deploy at zero cost.

Scope, deliberately narrow
-------------------------
This is for **documents** (SOP PDFs). It is NOT suitable for video: a 100 MB
video in a Postgres row would bloat the database, slow every backup, and be
pushed through memory on each read. Video stays link-based (YouTube/Vimeo/direct
CDN URL), which is the better design at this scale regardless.
"""
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _msg
from django.core.files.storage import Storage
from django.db import IntegrityError
from django.utils.deconstruct import deconstructible

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


class UploadTooLarge(Exception):
    pass


class UploadNotAllowed(Exception):
    pass


@deconstructible
class DatabaseUploadStorage(Storage):
    # Without @deconstructible, `makemigrations` cannot serialise a storage
    # instance into the AlterField for Lesson.pdf_file.

    max_bytes = MAX_UPLOAD_BYTES
    allowed_types = frozenset(ALLOWED_CONTENT_TYPES)
    extensions = (".pdf",)

    def _open(self, name, mode="rb"):
        row = self._model().objects.get(name=name)
        return ContentFile(bytes(row.content), name=name)

    def _save(self, name, content):
        data = content.read()
        size = len(data)
        if size == 0:
            raise UploadNotAllowed(_msg("The uploaded file is empty."))
        if size > self.max_bytes:
            raise UploadTooLarge(_msg(
                "That file is too large. Maximum size is {limit} MB."
            ).format(limit=self.max_bytes // (1024 * 1024)))
        ctype = (getattr(content, "content_type", "") or "").lower()
        lowered = name.lower()
        if ctype and ctype not in self.allowed_types and not lowered.endswith(self.extensions):
            raise UploadNotAllowed(_msg("Unsupported file type."))

        model = self._model()
        try:
            model.objects.create(name=name, content=data,
                                 content_type=ctype or "application/octet-stream", size=size)
        except IntegrityError:
            # Name collision after a concurrent upload: keep the newer bytes.
            model.objects.filter(name=name).update(content=data, size=size)
        return name

    def exists(self, name):
        return bool(name) and self._model().objects.filter(name=name).exists()

    def delete(self, name):
        if name:
            self._model().objects.filter(name=name).delete()

    def size(self, name):
        return self._model().objects.filter(name=name).values_list("size", flat=True).first() or 0

    def url(self, name):
        # The app serves /media/<name> through `protected_media`, which enforces
        # the same enrollment check as the lesson view. Pointing anywhere else
        # would either 404 or bypass authorization.
        return f"/media/{name}"

    def listdir(self, path):
        return [], []

    def _model(self):
        from apps.courses.models import StoredUpload
        return StoredUpload


MAX_VIDEO_BYTES = 25 * 1024 * 1024
VIDEO_CONTENT_TYPES = frozenset({"video/mp4", "video/webm", "video/ogg", "application/octet-stream"})


@deconstructible
class DatabaseVideoStorage(DatabaseUploadStorage):
    """Video uploads, same durability trade-off as documents but a bigger cap.

    Kept as a separate class (not a parameterised instance) so the migration can
    reference it by path and the two policies cannot drift.
    """

    max_bytes = MAX_VIDEO_BYTES
    allowed_types = VIDEO_CONTENT_TYPES
    extensions = (".mp4", ".webm", ".ogv", ".ogg", ".mov", ".m4v")
