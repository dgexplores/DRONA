# Roadmap — planned, not yet built

Work that has been **designed and agreed but deliberately not implemented**. Kept here so
the reasoning survives, and so nobody re-litigates a decision that was already made.

Last updated: 2026-09-27 · live commit at time of writing: `00963f5`

---

## 1. Watch-progress report — *"who watched how much"*

**Status:** ✅ **built and live** (2026-09-27) at `/analytics/watch-progress/`, with CSV export
at `/analytics/watch-progress/export/csv/`. Reached from the HR dashboard.

### What already exists

`LessonProgress` has been recording, per employee per lesson, since the video feature landed:

| Field | Meaning |
|---|---|
| `is_completed` | lesson finished |
| `last_position_seconds` | where they stopped |
| `watched_seconds` | how much they actually watched |
| `updated_at` | last activity |

The data is trustworthy by construction, in `LessonProgress` (`apps/courses/models.py`):

- `HEARTBEAT_MAX_SECONDS = 30` — one heartbeat can credit at most 30 s, so a hand-crafted
  request cannot claim a whole video in a single call
- the running total is clamped to `lesson_duration_seconds`, so repeated heartbeats can never
  inflate it past one full viewing
- the client's `completed` flag is **deliberately ignored** for video lessons
  (`save_lesson_progress` only calls `acknowledge()` for lessons that cannot be
  watch-verified, e.g. a PDF SOP)
- `COMPLETION_RATIO = 0.9` — 90 %, not 100 %, because the player heartbeats in ~10 s steps
  and a hard 100 % would block the certificate on the final partial step

`requires_watch_time` is `True` only for `lesson_type == 'video'` with a known duration, so
a PDF cannot auto-complete on zero watch time.

Unit-tested in `apps/courses/tests.py::LessonProgressWatchTests`.

### The gap that existed

`watched_seconds` was written to the database and **displayed nowhere**. The HR dashboard only
showed department-level completion rates, and the CSV export was the same shape. There was no
way to ask "did Raju finish part 3?"

### What was built

A per-employee × per-lesson grid, readable at a glance, behind the existing
`is_manager` gate (HOD or Super Admin), with a course selector:

| Employee | Lesson | Watched | Last position | Status |
|---|---|---|---|---|
| EMP001 | Everyday English Pt 1 | 9m 12s / 10m | 9:12 | 92 % ✓ |
| EMP002 | Everyday English Pt 1 | 2m 03s / 10m | 2:03 | 20 % |
| EMP003 | Workplace Etiquette Pt 1 | not started | 0:00 | — |

Plus the two roll-ups HR actually acts on:

- **not started** — enrolled, zero watch time
- **fell behind** — started, not finished, and no activity for 7 days
  (`STALE_AFTER_DAYS` in `apps/analytics/views.py`)

And a CSV export, one column pair per lesson, produced by the **same** helper the report uses
(`_watch_progress_rows`) so the screen and the export can never disagree.

Lessons that cannot be watch-verified (PDF SOPs, or a video with no duration) are **not**
grid columns — they would be meaningless. They collapse into a single "other" done/total
column instead. If a course has no watchable lesson at all, the page says so rather than
rendering an empty grid.

### Design notes worth keeping

- Read from `LessonProgress`, never recompute from the UI.
- `watched_seconds` is capped at lesson duration — a percentage is safe to display directly,
  and the report clamps anyway rather than relying on that alone.
- Bilingual: the report is fully translated (400 messages, 0 fuzzy, 0 untranslated).

### Known limitation — not fixed

**Any manager sees every department.** The gate is the existing `is_manager` check, matching
`hr_dashboard_view`, so an HOD can view other departments' watch data. The roadmap originally
promised HOD scoping; it was not implemented, because scoping *only* this screen would create
a misleading half-applied privacy model while the existing HR dashboard still lists everyone.
If department scoping is wanted, do it across the analytics views in one change, not here.

---

## 2. YouTube-hosted lessons — *deferred by choice*

**Status:** the tracking **works today**; the team has chosen not to use YouTube as the
primary source yet.

This is a deliberate product decision, not a technical limitation. Everything needed is
already built and proven on production:

- `apps/courses/video.py` recognises YouTube in every URL shape (`watch`, `youtu.be`,
  `/embed`, `/shorts`, `m.`) and renders an `iframe` instead of a `<video>` element
- `enablejsapi=1` lets the page read playback position, so **progress tracks identically**
  to an uploaded file
- CSP allows `www.youtube.com` for the IFrame API
- `static/js/app.js` shares one `makeReporter()` between both sources, so the throttling and
  completion rules cannot drift apart

**Why defer:** host the files ourselves where possible, keep the content in one place, and
avoid depending on a third party's embed policy. The nine Everyday English / Workplace
Etiquette clips are uploaded and working.

**Revisit if:** the video library grows past what the database should hold (see §4).

---

## 3. Google Drive links — **cannot be position-tracked**

**Status:** decided against, for a hard technical reason. Recorded so it is not retried.

Drive embeds are cross-origin `iframes`. The browser's same-origin policy means the page
**cannot read anything** from inside a Drive frame — not playback position, not duration, not
play state. Google publishes no player API that exposes them either.

So a Drive link can only ever record **opened / not opened**. It cannot report "watched 40 %",
cannot resume, and cannot satisfy the 90 % completion rule that issues certificates.

If Drive links are ever needed anyway, the honest implementation is a third source in
`resolve_video()` (`apps/courses/video.py`) that tracks *opened* only, and that **states the
limitation in the UI** rather than silently reporting 0 % watch time.

That wording already exists and can be reused verbatim: the non-YouTube embed branch of
`templates/courses/lesson.html` renders *"Playback position cannot be tracked for embedded
videos, so this lesson is marked complete when you open it."* Vimeo is the live proof of the
same limitation — `resolve_video()` returns `provider: "vimeo"` with no position API, so it
falls into that branch and behaves correctly by being honest about it.

A Drive link would land in that same branch for free, **if** a Drive URL were recognised
before the `kind: "file"` fallback. Note that fallback is a trap: an unrecognised URL is
handed to a `<video>` element as if it were a direct media file, which silently fails to
play. Any new embed source must be matched *before* that fallback.

---

## 4. Move video off the database — *needed before a real library*

**Status:** fine today, will not scale.

The nine training clips total **54 MB** and the database is now **68 MB** (from 10 MB). That
is comfortable. It stops being comfortable for a real video library, because every backup
carries the video and every read pushes bytes through a single gunicorn worker.

Thresholds to watch:

| Situation | Do this |
|---|---|
| A few dozen short clips (today) | keep in the database |
| Clips getting large, or dozens+ | paid Render disk (`render.yaml` has no `disk:` block — free tier cannot have one) |
| A real library, or anything long | external object storage: Cloudflare R2, Supabase Storage, S3 |

A disk or object store is a drop-in replacement, not a rewrite: `Lesson.pdf_file` and
`Lesson.video_file` both go through `apps/courses/storage.py`, so swapping the storage
backend changes where bytes live and nothing else. The Range-request view
(`apps/courses/views.py:_range_response`) is what a bucket would need to keep serving
`206 Partial Content` — object stores do this natively.

---

## Also parked, from earlier

- **Email delivery** — the reminder scheduler runs, but there are no SMTP credentials, so mail
  goes to the log. Needs `DJANGO_EMAIL_BACKEND` + host/port/user/password on the service.
  Tracked in `HANDOFF.md` §3a.
- **Clerk SSO** — removed 2026-09-26, kept as documented future scope in the README.
- **Bulk staff import CSV** — built and live.
