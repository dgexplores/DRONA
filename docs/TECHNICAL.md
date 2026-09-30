# SRMS Drona — Technical Deep Dive

Everything about how the system actually works, written to be understood rather
than memorised. This document explains the **mechanics**: what happens on the
server, in what order, and why each decision was made.

It complements two other documents:

- [`docs/PROJECT-GUIDE.md`](PROJECT-GUIDE.md) — the high-level "what and why"
- [`docs/presentation/SCRIPT.md`](presentation/SCRIPT.md) — the spoken script

Every behaviour described here was read out of the source at the commit that
published this file. File paths and constant names are given so you can verify
any claim yourself.

---

## Table of contents

1. [The 60-second version](#1-the-60-second-version)
2. [The shape of the system](#2-the-shape-of-the-system)
3. [How a request flows through the app](#3-how-a-request-flows-through-the-app)
4. [Accounts, roles and sessions](#4-accounts-roles-and-sessions)
5. [Rate limiting — and how it was bypassed](#5-rate-limiting--and-how-it-was-bypassed)
6. [The bilingual system](#6-the-bilingual-system)
7. [Courses: the content model](#7-courses-the-content-model)
8. [Video lessons and HTTP Range](#8-video-lessons-and-http-range)
9. [Progress: derived, never trusted](#9-progress-derived-never-trusted)
10. [File uploads and the stored-XSS bug](#10-file-uploads-and-the-stored-xss-bug)
11. [Quizzes and grading](#11-quizzes-and-grading)
12. [AI question generation](#12-ai-question-generation)
13. [Certificates, QR codes and public verification](#13-certificates-qr-codes-and-public-verification)
14. [Analytics and CSV export](#14-analytics-and-csv-export)
15. [Notifications and the scheduler](#15-notifications-and-the-scheduler)
16. [Security posture](#16-security-posture)
17. [Testing](#17-testing)
18. [Deployment](#18-deployment)
19. [Known limits and honest gaps](#19-known-limits-and-honest-gaps)
20. [Where the code lives](#20-where-the-code-live)

---

## 1. The 60-second version

It is a Django web application. The browser asks for a page; the server builds
the finished HTML and sends it. There is no JavaScript framework and no
front-end build step.

Content is organised as **Category → Course → Module → Lesson**. A staff member
is enrolled in a Course. As they work through Lessons, the server records what
they actually did, and from that it **derives** a progress percentage and
decides whether they have earned a certificate.

Three ideas do most of the work:

| Idea | Why it matters |
|---|---|
| **Progress is derived, never accepted** | The browser can claim anything. The server decides. A user cannot make themselves 100% by editing a request. |
| **Watch time is accumulated server-side** | A `<video>` element lies — you can seek to the end in one click. The server counts what it was actually sent. |
| **The certificate gate is two conditions** | You must complete the lessons *and* pass the quiz. Neither alone is enough. |

---

## 2. The shape of the system

```
apps/
  users/          accounts, roles, login, language preference, HR enrolment
  courses/        content, enrolment, progress, video serving, uploads
  quizzes/        quizzes, questions, attempts, AI generation
  certificates/   issuance, PDF, QR, public verification
  analytics/      watch-progress report, HR dashboard, CSV
  notifications/  scheduled reminders, audit-log pruning
  management/     audit log, admin operations
srms_dorna/       settings, URLs, WSGI, custom middleware
templates/        38 server-rendered HTML templates
static/           custom CSS and vanilla JS
locale/hi/        401 translated interface strings
```

Seven Django applications, each owning its own models, views and tests. This is
"app-per-domain", not one large module. The boundary is what makes the 203-test
suite possible — tests for certificates do not need to know anything about
analytics.

### The stack, and why each piece

| Piece | Choice | Reason |
|---|---|---|
| Framework | Django 6.0.8 | Security built in (CSRF, sessions, ORM escaping), admin, mature |
| Language | Python 3.12 in production | — |
| Database | PostgreSQL (prod), SQLite (dev/test) | Constraints and concurrent writes in prod; zero-setup locally |
| Templates | Server-rendered HTML | Small payloads, works without JS, good on a cheap phone |
| Hashing | Argon2-cffi | Memory-hard: expensive to attack even with GPUs |
| Serving | Gunicorn + WhiteNoise | Production WSGI server; assets without a separate CDN |
| Scheduling | APScheduler | In-process periodic jobs |

### Middleware stack

Order matters, and it is deliberate
(`srms_dorna/settings.py:52`):

```
SecurityMiddleware
  → WhiteNoiseMiddleware
    → SecurityHeadersMiddleware      ← ours
      → SessionMiddleware
        → LocaleMiddleware
          → CommonMiddleware
            → CsrfViewMiddleware
              → AuthenticationMiddleware
                → UserLanguageMiddleware   ← ours
                  → MessageMiddleware
                    → XFrameOptionsMiddleware
```

`UserLanguageMiddleware` **must** sit after `AuthenticationMiddleware` because
it reads the logged-in user's saved language preference.

---

## 3. How a request flows through the app

Take "a staff member opens their dashboard".

1. **Browser** sends `GET /dashboard/`.
2. **`SecurityMiddleware`** — HTTPS redirect, HSTS, secure cookie flags.
3. **`SessionMiddleware`** — loads the session cookie, opens the session store.
4. **`UserLanguageMiddleware`** — decides active language: session override →
   saved user preference → browser header. Sets it for this request.
5. **`AuthenticationMiddleware`** — loads the user from the session. No session
   user, so the view's `@login_required` redirects to `/login/`.
6. **The view** runs a query: the user's enrolments, each with progress
   recalculated.
7. **`CsrfViewMiddleware`** — verified on any POST.
8. **Template renders** — Django escapes interpolated values by default, so
   course titles containing `<script>` render as text, not markup.
9. **Response** goes back out through the stack, security headers applied.

The same request in reverse order handles the response. That is why the
middleware order above is not alphabetical.

---

## 4. Accounts, roles and sessions

### The user model

`StaffUser` (`apps/users/models.py`) extends Django's `AbstractUser` with one
important change:

```python
USERNAME_FIELD = 'employee_id'
```

The login identifier is the **employee ID**, not an email. Non-teaching staff
should not need an email address to use a training portal, and it makes the
account survive a person changing their name spelling.

Custom fields: `employee_id` (unique, validated), `department`, `role`,
`preferred_language`, `phone_number`, `designation`.

### The three roles

```python
ROLE_CHOICES = (
    ('staff', 'Non-Teaching Staff'),
    ('hod',   'Head of Department'),
    ('admin', 'Super Admin'),
)
```

Two helper properties collapse the checks so no view re-implements them:

```python
@property
def is_manager(self):     # HOD, admin, or Django staff/superuser
@property
def is_super_admin(self): # admin role or superuser
```

**Important:** these are used for *display and navigation* decisions. The real
enforcement is a permission check inside each view. Hiding a menu item is a
courtesy, not a security control — the guide for this codebase
(`ENGINEERING.md`) is explicit about that.

### Passwords

```python
PASSWORD_HASHERS = ['django.contrib.auth.hashers.Argon2PasswordHasher', ...]
```

Argon2 is **memory-hard**: cracking a hash needs both CPU *and* a lot of RAM, so
GPU farms and ASICs lose their advantage. The stored value is a salted hash,
never the password.

### Sessions

Server-side sessions, not JWTs. This is a deliberate choice: with a server-side
session, "log out" destroys real server state, so a copied cookie is useless
after logout. With a JWT you cannot revoke it before expiry without adding a
denylist — which is just a server-side session with extra steps.

---

## 5. Rate limiting — and how it was bypassed

Login, registration and password reset are throttled with `django-ratelimit`:
**5 attempts per 5 minutes**.

### The bug that shipped

The limiter was keyed on `get_client_ip`, which returned the **first
`X-Forwarded-For` entry**. The comment in the code explains why that is wrong
(`apps/users/views.py:30`):

> Every value here is attacker-controlled: `X-Forwarded-For` is set by the
> client, and the app sits behind a proxy that *appends* to it. Taking the
> first XFF entry therefore let anyone mint a fresh rate-limit bucket per
> request by sending a different header.

It was confirmed live, not theorised: **six bad logins with six spoofed XFF
values all returned 200 and never 429.**

### The fix

Order changed so the address is resolved from a value the client cannot choose —
`REMOTE_ADDR` first, with proxy-aware handling. The real client IP comes from
the server's own connection, not a header.

### The lesson

A rate limiter is only as strong as its key. If an attacker picks the key, the
limit is decorative. This is the class of bug you find by *testing a control
against an actual attacker*, not by reading that the control exists.

---

## 6. The bilingual system

English and हिन्दी, throughout, with content fields carrying both languages
side by side.

### 401 translated strings

`locale/hi/LC_MESSAGES/django.po`, compiled to `.mo`. Verified with
`msgfmt --statistics`:

```
401 translated messages.
```

**A counting trap worth knowing.** Naive counts give wrong answers:

| Method | Result | Why it is wrong |
|---|---|---|
| `grep -c '^msgid'` | 402 | Counts the `.po` header entry as a message |
| `grep -v '^msgid ""$'` | 381 | Misses multi-line entries, which start `msgid ""` then continue |
| **`msgfmt --statistics`** | **401** | The authority |

This project published "402" on a slide and in its report before the correct
method was used. `msgfmt` is the tool to trust.

### How the active language is decided

`UserLanguageMiddleware` (`srms_dorna/middleware.py:66`) resolves priority:

```
session override  >  saved user preference  >  browser Accept-Language
```

It exists because of two real gaps:

1. `LocaleMiddleware` reads the `django_language` **cookie** and
   `Accept-Language` — it no longer reads `request.session['django_language']`,
   which is exactly what the language toggle writes. So the toggle set the
   session, the page reported `lang="hi"`, and every `{% trans %}` still
   rendered English.
2. Templates used an `is_hindi` context variable, and when the session was empty
   the fallback to the saved preference had nowhere to live — so a Hindi user on
   a fresh session got English chrome.

### Bilingual content, not just bilingual chrome

Course titles, descriptions and module text have `*_en` and `*_hi` fields. The
interface being translated is only half the requirement — the *content* must
exist in both languages for a Hindi-preference user to get anything useful.

---

## 7. Courses: the content model

```
Category
  └── Course
        └── Module
              └── Lesson   (video | pdf | text)
```

`Course` carries the flags that drive behaviour: `is_mandatory` (triggers
reminders) and `is_published` (controls visibility).

A `Lesson` has a `lesson_type` and, for video, a `duration_minutes`. That
duration is the basis for all watch-time verification, which is why it must be
set — see §9.

`Enrollment` joins a user to a course and carries the derived state:
`progress_percent`, `is_completed`, `completed_at`, `watch_seconds`, and
`last_reminded_at` (used purely for reminder de-duplication).

Two uniqueness constraints matter:

- `Enrollment`: unique per `(staff_user, course)` — cannot enrol twice
- `LessonProgress`: unique per `(enrollment, lesson)` — one row per lesson

---

## 8. Video lessons and HTTP Range

### Why Range matters

When you scrub a video, the browser does not download the file. It sends:

```
Range: bytes=1048576-2097151
```

and expects a `206 Partial Content` with just that slice. Several browsers
**refuse to play at all** if the server replies `200` with the whole file.

Without Range: seeking re-downloads megabytes. With Range: a seek is a small
transfer.

### The implementation

`apps/courses/views.py:331`, `_range_response()`:

```python
total = len(data)
m = re.match(r'bytes=(\d*)-(\d*)$', request.headers.get('Range',''))
```

It handles:

| Header form | Meaning | Handled |
|---|---|---|
| `bytes=0-1023` | Explicit range | start/end set |
| `bytes=1024-` | Open-ended | end = last byte |
| `bytes=-500` | Suffix — "last 500 bytes" | start = total − 500 |
| `bytes=99999-` | Beyond EOF | `416 Range Not Satisfiable` + `Content-Range: bytes */<total>` |
| absent | Whole file | `200 OK` |

Bytes are yielded in 256 KB chunks through a `StreamingHttpResponse`, so a large
video is never held in a single response buffer.

Two hardening details:
- `filename = os.path.basename(filename)` — strips any path component from the
  filename before it reaches the `Content-Disposition` header
- Content type is resolved with `mimetypes.guess_type` on the **stored** name,
  not from the client

---

## 9. Progress: derived, never trusted

This is the most important mechanism in the project.

### The rule

The browser sends a heartbeat roughly every 10 seconds. The server decides what
that is worth. From `apps/courses/models.py`:

```python
class LessonProgress(models.Model):
    COMPLETION_RATIO = 0.9          # 90% of duration counts as complete
    HEARTBEAT_MAX_SECONDS = 30      # ceiling on a single heartbeat
```

### Why 90% and not 100%

The comment in the code gives the reason:

> Deliberately not 1.0: the player heartbeats in ~10s steps, so the final partial
> step would leave a legitimately-watched lesson just under 100% and block the
> certificate.

A 10-minute video heartbeats every 10s. Requiring exactly 100% of 600s means
the last heartbeat is 20s of "over-credit" that never arrives. 90% tolerates
seeking back and re-watching while still demanding real engagement.

### How a heartbeat is handled

`apps/courses/views.py`, the heartbeat endpoint:

```python
credited = progress.register_watch(data.get('watched', 0))
```

`register_watch` (`apps/courses/models.py`) does four things:

```python
seconds = max(0, min(seconds, self.HEARTBEAT_MAX_SECONDS))   # 1. clamp
before  = self.watched_seconds
self.watched_seconds = min(before + seconds, self.lesson_duration_seconds)  # 2. cap
credited = self.watched_seconds - before                      # 3. report delta
if self.watched_seconds >= self.required_watch_seconds:       # 4. derive
    self.is_completed = True
```

So: a single heartbeat can credit **at most 30 seconds**, and the running total
can **never exceed the lesson duration**. Sending `watched=99999` credits 30
seconds, then 0 forever after. You cannot mint an hour of watch time in one
request.

### The anti-forgery line

Inside the same view, with an explicit comment:

> Completion is derived from server-accumulated watch time only. The
> client-supplied `completed` flag is deliberately ignored here so a
> hand-crafted request cannot mint a certificate.

For **video lessons with a known duration**, the `completed` flag from the
client is thrown away.

For **PDF lessons and lessons with no duration**, watch time cannot be verified,
so completion falls back to `acknowledge()` — an explicit user action. The
alternative, auto-completing on zero watch time, would mean a certificate for a
document nobody opened.

### Course progress

`Enrollment.update_progress()`:

```python
total = self.course.get_total_lessons()
completed = LessonProgress.objects.filter(enrollment=self, is_completed=True).count()
self.progress_percent = int((completed / total) * 100)
if self.progress_percent >= 100 and not self.is_completed:
    self.is_completed = True
    self.completed_at = timezone.now()
```

Recalculated from lesson rows every time it is called — it is never trusted from
the client and never drifts.

### Concurrency

Progress recalculation runs inside a transaction with row locking:

```python
with transaction.atomic():
    enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
    enrollment.update_progress()
```

Without `select_for_update`, two simultaneous heartbeats could interleave a
read-modify-write and lose one update.

### Progress vs watch time — deliberately different

| Field | Meaning |
|---|---|
| `watched_seconds` | Time actually sent by the server, capped at duration |
| `last_position_seconds` | Where the player is — resume point, **not** proof of watching |
| `progress_percent` | Derived from completed lessons |

The split lets analytics distinguish "watched it" from "opened it and left the
tab". `last_position_seconds` is attacker-controlled, so it is never used for
completion.

---

## 10. File uploads and the stored-XSS bug

### The validation rule

`apps/courses/storage.py` — uploads land in a database row, not the filesystem.

```python
ext_ok   = lowered.endswith(self.extensions)
ctype_ok = (not ctype) or ctype in self.allowed_types
if not (ext_ok and ctype_ok):
    raise UploadNotAllowed(...)
guessed = mimetypes.guess_type(lowered)[0]
ctype = guessed if guessed in self.allowed_types else "application/octet-stream"
```

Two things: both signals must agree (**and**, not **or**), and the stored type
is **re-derived from the extension**. The client-declared type is never
persisted.

### The bug

The original used `or`:

```python
if not (ext_ok or ctype_ok):   # ← the bug
```

So a file named `evil.mp4` declaring `Content-Type: text/html` passed on the
**extension alone**, was stored verbatim, and `lesson_video_view` later served it
as `text/html` with `Content-Disposition: inline`. The browser rendered it as an
HTML page — a stored XSS on a route that serves whatever the uploader supplied.

It was proven with a test, not reasoned about: a row storing
`content_type: text/html` over bytes `b'<script>alert(1)</script>'`.

### Other guards on that path

- Non-empty and size-capped before anything else
- `IntegrityError` on a name collision from a concurrent upload is caught — the
  newer bytes win rather than the upload 500-ing
- PDF storage restricted to `.pdf`; video storage to `.mp4 .webm .ogv .ogg .mov .m4v`

---

## 11. Quizzes and grading

`Quiz.passing_score` is a percentage, default **70**.

`apps/quizzes/views.py:38`, `submit_quiz_view`:

```python
score_percent = round((correct_count / total_q) * 100, 1)
passed = score_percent >= quiz.passing_score
```

`QuizAttempt` stores `score`, `passed`, and the answers, so a result is a record,
not a recomputation that can change.

The result page branches three ways, and the middle branch is the important one:

| Condition | Message |
|---|---|
| `passed and progress >= 100` | Certificate issued |
| `passed` but progress < 100 | "Complete remaining video/PDF lessons to receive your certificate." |
| not passed | Score, threshold, retry |

So a user can pass the quiz and still not have a certificate. That is the
two-condition gate working.

---

## 12. AI question generation

An administrator uploads an SOP document or pastes text; Gemini returns
multiple-choice questions with answer keys and explanations.

### Never auto-published

Generated questions become a **draft**. An administrator reviews and edits
before any learner sees them. The AI accelerates authoring; it does not decide
what is taught.

### Model fallback chain

```python
DEFAULT_GEMINI_MODELS = (
    'gemini-3.5-flash',
    'gemini-3.1-flash-lite',
    'gemini-2.5-flash',
    'gemini-3-flash-preview',
)
```

Models are tried in order. The code comments on why this is not over-engineering:
models get retired without warning, and without a chain a retirement would
silently degrade the feature. `GEMINI_MODEL` pins a single model if you want to.

### Output normalisation

The interesting part is `_normalise_questions()` (`apps/quizzes/gemini_services.py:97`).
Its docstring states the requirement:

> A malformed model response must not reach the database as a broken quiz, and
> must not silently reduce the count without the caller knowing.

Each item is dropped unless it is a dict with a non-empty stem, a list of option
dicts, **at least two** options, and **exactly one** option marked correct.

That last check matters: a question with two correct answers is unanswerable, and
one with none is unpassable. Both are rejected before they can reach the
database. The parser also strips the markdown fences models wrap JSON in.

### Reporting

`GenerationReport` records what actually happened — which model was used, whether
it fell back, whether the response was truncated, how many were created. Degradation
is **visible**, not silent.

---

## 13. Certificates, QR codes and public verification

### ID format

```python
def generate_cert_id():
    return f"SRMS-CERT-{year}-{uuid.uuid4().hex[:8].upper()}"
```

UUID4-derived, so IDs are unguessable and not sequential. The card is
`unique=True`, giving a unique index for the verification lookup.

Note: these are **not hashed**. A hash would be irreversible and then the
verification page could not look the certificate up by ID. It is a public
lookup token by design.

### Issuance gate

`passed and enrollment.progress_percent >= 100` — both conditions.

### PDF and QR

`generate_certificate_pdf()` builds a ReportLab document and embeds a QR code
(`error_correction=M`) encoding the verification URL for the running host.

### Public verification, and the privacy problem it creates

`verify_certificate_view` is **unauthenticated by design** — that is the point
of a QR on a printed certificate. But an unguessable ID plus a public endpoint
means anyone holding a certificate ID could enumerate the staff roster.

Hence `_masked_name()` (`apps/certificates/views.py:59`):

> The verification page is public by design — it is what the QR code on a
> printed certificate resolves to — so it must confirm a match without
> publishing a full staff roster to anyone who holds a certificate ID.

It returns first name plus last initial — `Anant S.` — and falls back to
"SRMS staff member" when names are empty. A certificate can be shown publicly
without exposing the holder.

---

## 14. Analytics and CSV export

### Watch-progress report

Per-lesson, per-user watch time, ranked by **watch activity** rather than
enrolment count — a commit (`293f173`) fixed exactly that, because ranking by
enrolment surfaced courses nobody was actually using.

Duration is formatted mm:ss (`_mmss`), because a raw second count is not
readable.

### HR dashboard

Completion and participation across staff, scoped by permission: HOD sees their
department, Super Admin sees everything.

### CSV export

`export_watch_progress_csv` and `export_staff_report_csv` stream a generated
CSV so HR can take the data into a spreadsheet. The generators are lazy
(`rows()`), so a large export does not build the whole file in memory.

---

## 15. Notifications and the scheduler

`apps/notifications/scheduler.py` runs two APScheduler jobs:

| Job | Schedule | Purpose |
|---|---|---|
| `send_pending_reminders` | Every `SRMS_REMINDER_INTERVAL_HOURS` (default 24h) | Email staff with incomplete mandatory training |
| `prune_auditlog_job` | Daily | Trim the audit log |

The reminder query is careful:

```python
Enrollment.objects.filter(
    is_completed=False, course__is_mandatory=True, staff_user__is_active=True
).filter(Q(last_reminded_at__isnull=True) | Q(last_reminded_at__lt=cutoff))
.order_by('last_reminded_at', 'enrolled_at', 'id')[:50]
```

- Only **mandatory** courses, not optional ones
- Only **active** staff
- The `last_reminded_at` window prevents repeat spam
- Oldest-first ordering, so the most overdue get reminded first
- Capped at 50 per run

### Why it is switched off

```python
if not getattr(settings, 'SRMS_RUN_SCHEDULER', False):
    logger.warning("Scheduler disabled (set SRMS_RUN_SCHEDULER=1 to enable).")
    return
```

Two reasons. First, on a multi-worker gunicorn deployment every worker would
start a scheduler and reminders would be sent N times. Second — and this is the
part worth copying — it **logs at WARNING, not INFO**:

> with SRMS_RUN_SCHEDULER unset no reminders are ever generated, so say so at
> WARNING, not INFO.

A subsystem that silently never runs is worse than one that announces it is off.

**Current status:** the code is complete, but `SRMS_RUN_SCHEDULER` defaults to
`0` and the email backend defaults to the console, because the institute has not
issued SMTP credentials. **No reminder emails are currently being sent.**

---

## 16. Security posture

### What is on

| Control | Setting |
|---|---|
| Password hashing | Argon2 (memory-hard) |
| Sessions | Server-side, so logout really invalidates |
| CSRF | On every POST |
| Clickjacking | `X_FRAME_OPTIONS = DENY` |
| MIME sniffing | `SECURE_CONTENT_TYPE_NOSNIFF = True` |
| HTTPS | `SECURE_SSL_REDIRECT` in production |
| HSTS | 1 year, include-subdomains, preload |
| Secure cookies | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` |
| Brute force | 5 per 5 min on login, register, reset |
| Audit log | Administrative actions recorded |
| Uploads | Extension **and** type must agree; type re-derived server-side |
| Permissions | Enforced in views, not by hiding UI |

### Fails closed in production

```python
if not DEBUG:
    if DJANGO_SECRET_KEY in ('', _INSECURE_DEFAULT_SECRET_KEY):
        raise ValueError(...)
    if ALLOWED_HOSTS == ['*']:
        raise ValueError(...)
```

The app **refuses to boot** with a default secret key or a wildcard host in
production. A misconfigured deploy fails immediately and visibly rather than
serving an insecure site quietly.

### The three vulnerabilities found and fixed

Full detail is in the commit messages; the transferable lesson is in §5.

| # | Bug | Root cause | Fix |
|---|---|---|---|
| 1 | Stored XSS on media routes | `or` instead of `and` between extension and declared type; declared type trusted | Both must agree; type re-derived from extension. Also cleared 17 dependency advisories |
| 2 | Rate-limit bypass | Limiter keyed on client-controlled `X-Forwarded-For` | Real client IP resolved from a value the client cannot choose |
| 3 | Live credentials in a public repo | README listed real accounts; live passwords equalled employee IDs | 14 unique generated passwords, admin secret rotated, credentials moved to the macOS keychain |

None were found by reading a checklist. Each was found by testing a control
against an actual attacker. Each has a **regression test**, so the fix cannot
silently rot.

`pip-audit` currently reports **no known vulnerabilities**, and every
dependency is pinned to an exact version.

---

## 17. Testing

**203 tests. Run on every push and pull request. A change cannot land while red.**

### Distribution

| Area | Tests |
|---|---|
| `users` | 54 |
| `management` | 31 |
| `courses` | 59 (23 + 12 range + 9 video + 15 storage) |
| `quizzes` | 21 |
| `analytics` | 20 |
| `certificates` | 17 |
| `notifications` | 1 |

### Running them

```bash
python manage.py test apps --settings=srms_dorna.test_settings
```

`test_settings` uses SQLite, so no database server is needed. A local run
completes 203 tests in about 1.5 seconds.

### What is actually asserted

Not "does it return 200" — the assertions encode behaviour:

- **Range responses** — `206` for a valid range, `200` for none, `416` past EOF,
  correct `Content-Range`, correct byte content
- **Watch-time anti-forgery** — a spoofed `completed` flag does not complete a
  video lesson; a `watched` value beyond `HEARTBEAT_MAX_SECONDS` credits at most
  30 seconds; the total cannot exceed the duration
- **Progress derivation** — recalculation from lesson rows, the 100% boundary,
  `completed_at` stamping
- **Upload validation** — a file whose extension and content type disagree is
  rejected
- **Quiz generation** — malformed model output is dropped, two-correct-answer
  items are rejected
- **Verification** — surname masking, unknown ID returns a not-valid page rather
  than a 500
- **Permissions** — a staff user cannot read another user's results

### The property that matters

Not the count — that each security fix has a **regression test that fails if the
bug returns**. `ENGINEERING.md` records the principle: a test that encodes the
vulnerability as its specification is what stops a fix rotting.

### What is not tested

- **No load or concurrency testing.** Nothing here proves behaviour under real
  institutional load.
- **No accessibility audit** of the video player or quiz controls.
- **Gemini is tested against recorded and malformed responses**, not a live
  model on every run.
- **Email delivery is untested end to end** — no SMTP credentials exist.

---

## 18. Deployment

- **Hosting:** Render free web service, `https://dronav2.onrender.com`
- **Database:** externally managed PostgreSQL
- **Static assets:** WhiteNoise, no separate CDN
- **Health check:** `/health/`

### The boot sequence

```bash
set -e;
python manage.py boot;
gunicorn srms_dorna.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

One consolidated `boot` step runs migrations, creates the cache table, and syncs
the admin password. The comments record why:

> the previous form spawned three separate manage.py invocations (three Django
> boots, ~90s) before gunicorn, which dominated free-plan cold starts. A failed
> step still propagates (never `|| true`).

`set -e` matters: a migration that fails must stop the boot, not be swallowed
and followed by gunicorn serving a broken schema.

### CI

`.github/workflows/ci.yml` on every push and pull request:

1. `manage.py check`
2. `makemigrations --check --dry-run` — catches an un-migrated model change
3. **the 203-test suite**
4. `collectstatic` — a build check
5. `compileall` — a fast syntax gate

Render auto-deploys from `main` on commit.

### Known constraints

- **Free plan, single instance** — which is why the scheduler is off by default
- **Media on local disk** — fine at this scale, move to object storage before
  real load
- **Render Blueprint has Auto Sync off** — editing `render.yaml` does not change
  production until a sync is run deliberately

---

## 19. Known limits and honest gaps

1. **Email is not live.** Code complete; `SRMS_RUN_SCHEDULER=0` and a console
   email backend, because the institute has issued no SMTP credentials. No
   reminders are being sent.
2. **No load testing.** Nothing proves behaviour under real load.
3. **No accessibility audit** of interactive components.
4. **Two response-time figures were measured, not benchmarked** — single
   observations on a cold-start-prone free-tier host, not a performance study.
5. **Media on local disk** rather than object storage.
6. **A course with no lessons reports 100% progress.** `update_progress()`
   returns 100 when `total_lessons == 0`, so an empty course looks complete
   rather than broken. Worth changing if empty courses become possible.
7. **Report front matter, UAT responses and signatures** are authored material
   needing supervisor verification before academic submission.

---

## 20. Where the code lives

| Question you are asking | File to open |
|---|---|
| How is progress calculated? | `apps/courses/models.py` — `Enrollment.update_progress`, `LessonProgress` |
| What stops someone faking progress? | `apps/courses/views.py` — heartbeat endpoint |
| How is video served? | `apps/courses/views.py` — `_range_response` |
| How are uploads validated? | `apps/courses/storage.py` |
| How does login work? | `apps/users/views.py`, `apps/users/models.py` |
| How is language chosen? | `srms_dorna/middleware.py` — `UserLanguageMiddleware` |
| How are security headers set? | `srms_dorna/settings.py`, `srms_dorna/middleware.py` |
| How are quizzes graded? | `apps/quizzes/views.py`, `apps/quizzes/models.py` |
| How does AI generation work? | `apps/quizzes/gemini_services.py` |
| How are certificates made? | `apps/certificates/pdf_builder.py`, `apps/certificates/views.py` |
| What do reports show? | `apps/analytics/views.py` |
| How do reminders work? | `apps/notifications/scheduler.py` |
| What is deployed and how? | `render.yaml`, `runtime.txt`, `.github/workflows/ci.yml` |
| What traps has this code hit? | `ENGINEERING.md` |
| Operational state | `HANDOFF.md` |
| Deferred work | `ROADMAP.md` |

---

## Companion documents

- [`PROJECT-GUIDE.md`](PROJECT-GUIDE.md) — the high-level project explanation
- [`presentation/SCRIPT.md`](presentation/SCRIPT.md) — the spoken presentation script
- [`report/report3.0.pdf`](report/report3.0.pdf) — the full 51-page report
- Source: <https://github.com/dgexplores/DRONA>
- Live: <https://dronav2.onrender.com>
