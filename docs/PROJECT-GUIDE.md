# SRMS Drona — Project Guide

A plain-language explanation of what this project is, why it exists, how it
works, how it is built, and how it is tested. Written to be read start to
finish by someone who has never seen the codebase.

Every figure here was checked against the code on the commit that published
this file.

---

## 1. What is it?

**SRMS Drona is a learning management web application for the non-teaching
staff of a college** — clerks, accounts staff, library staff, administrative
officers, lab assistants, and everyone else who works at the institution but
is not a student and does not teach.

It is a closed, internal training system. Staff sign in, complete the courses
assigned to them, take a quiz, and receive a certificate. Their Head of
Department and the platform administrators can see who has completed what.

It is **not** a public course-selling platform, not a student portal, and not a
video-hosting service. It is an internal compliance-and-training record system
with a learning interface on the front.

The name comes from *Drona* — a Sanskrit term for a teacher or guide. Drona is
the student-facing learning workspace; SRMS is the institution.

---

## 2. What is it for?

### The problem it solves

Institutional training material for support staff usually ends up scattered
across shared drives, outdated printed notes, and chat forwards. Three
consequences follow:

1. **It is hard to reach.** The intended user is often on a phone, on a patchy
   connection, between tasks.
2. **There is no record of completion.** A signature on a register proves
   attendance, not learning. Nobody can answer "who has completed workplace
   safety training?" with confidence.
3. **Administrators have no visibility.** They manage content but cannot see
   engagement, so they manage blind.

### What "solved" means here

The system turns "did they complete it?" from a **claim someone types in** into
a **fact the system derives**. When a lesson is marked complete, the database
row changes. Course progress is then recalculated from those rows on the
server. A user cannot reach 100% by editing a number in their browser.

The second thing it does is produce **verifiable proof**. A certificate carries
a QR code. Scanning it opens a public verification page — no login — that
confirms the certificate is real, for which course, and issued when. The
person's surname is masked so a certificate can be shown publicly without
exposing the holder.

---

## 3. Who uses it?

Three roles, enforced on the server. Each role has a genuinely different
capability set, not just a different menu.

| Role | What they can do |
|---|---|
| **Staff** (non-teaching employee) | See their own dashboard, open assigned courses, watch lessons, take quizzes, download their own certificates |
| **HOD** (Head of Department) | Everything a staff member can do, plus see and report on their own department, bulk-enrol staff into courses |
| **Super Admin** | Platform-wide: create and manage courses and content, manage all staff accounts, view HR analytics, export reports |

A staff member cannot see another person's results. This is enforced in the
view layer on the server and covered by tests — not by hiding links in the
interface.

---

## 4. What can it do? (features)

### Login and accounts
- Sign in with **employee ID + password**. Employee ID is the username field —
  staff do not need or want an email address to use a training portal.
- Passwords hashed with **Argon2**, a memory-hard algorithm chosen so that if
  the database is ever stolen, the hashes are expensive to attack even with
  GPUs.
- **Server-side sessions.** Logging out genuinely invalidates the session
  server-side, rather than just clearing a cookie.
- **Rate limiting** on login, registration and password reset, so password
  guessing is throttled.
- **Audit log.** Administrative actions are recorded.

### Courses and learning content
- Four-level content hierarchy: **Category → Course → Module → Lesson**.
- Course content is **bilingual**: fields carry both English and Hindi text
  side by side, so one course can be presented in either language or both.
- Courses can be marked **mandatory**, which is what drives reminders.
- Per-lesson completion is stored individually, which is what makes accurate
  progress possible.

### Video lessons, properly done
- Video is served through Django's **file response with HTTP Range support**.
  This is the detail that matters: Range support is what makes seeking instant
  and what makes it possible to store *where in the video* someone stopped.
- The player **remembers the resume position** per lesson, so a user closes the
  tab and returns to the same second, not to the beginning.
- Uploaded files are **validated at two independent points** — declared content
  type *and* file extension must agree — and the stored content type is
  re-derived from the extension rather than trusted from the client.

### Quizzes and assessments
- Multiple-choice quizzes attached to courses, with a configurable pass mark.
- Questions and options managed by administrators.
- Attempt tracking and results recorded per user.

### AI-assisted question generation
- An administrator uploads an **SOP document** (standard operating procedure,
  policy, circular) or pastes text.
- **Google Gemini** generates multiple-choice questions with answer keys and
  explanations.
- **Nothing is auto-published.** A generated quiz is a draft that an
  administrator reviews and edits.
- The parser handles real model behaviour: markdown-fenced JSON, malformed
  items (rejected before they can reach the database), and retired model
  versions (a fallback chain of stable model candidates).

### Progress tracking
- Progress percentage is **recalculated on the server** from completed lessons
  every time it is read.
- Reaching 100% sets the enrolment complete and stamps a completion time.
- Per-lesson watch time is recorded separately from lesson completion, which
  lets the analytics distinguish "watched it" from "opened it".

### Certificates
- Issued on successful completion and passing.
- **QR code** on the certificate links to a public verification page.
- Verification page works **without logging in** and **masks the surname**.
- Downloadable as PDF.

### Bilingual interface (English / हिन्दी)
- **401 translated interface strings**, hand-maintained, not machine-generated.
- A language toggle in the header; the choice is **stored on the user's
  account**, so it persists across devices and sessions.
- All navigation, forms, buttons, and error messages are covered.

### Analytics and reporting
- **Watch-progress report** — per-lesson watch time for a course, so a
  department can see where people drop off.
- **HR dashboard** — participation and completion across staff.
- **CSV export** for both the watch-progress report and the staff report, so
  data can leave the system for HR spreadsheets.
- Reports are filterable and permission-scoped.

### Notifications
- An **APScheduler** background job that finds staff with incomplete
  mandatory training and emails a reminder.
- Includes de-duplication (won't re-send within the configured interval),
  oldest-first ordering, and a per-run cap.
- **Current status, stated honestly:** the code is complete, but
  **delivery is not live**. The scheduler is disabled by default
  (`SRMS_RUN_SCHEDULER=0`) so it does not start in every web worker, and the
  email backend defaults to the console because the institute has not issued
  SMTP credentials. Until those are configured, no reminder emails are sent.
- There is also a separate finding in this area that the report is careful
  about: the system records a warning when the scheduler is disabled, because
  a subsystem that silently never runs is worse than one that says it is off.

---

## 5. How does it work? (the system, end to end)

Here is one person's journey, and what happens inside the system at each step.

**1. Account creation.** A Super Admin creates a staff account with employee
ID, department, designation, and role. The password is set to a generated
value — never a default derived from the employee ID.

**2. Login.** The user submits employee ID and password. The request is
rate-limited by IP. The password is hashed with Argon2 and compared against
the stored hash. On success the server creates a session and redirects to the
dashboard.

**3. Dashboard.** The server queries the user's enrolments and, for each,
recalculates progress from the individual lesson-progress rows. What you see is
computed at request time, not read from a stale counter.

**4. Opening a course.** The server checks the user is enrolled, then returns
the course with its modules, lessons, and the user's per-lesson state.

**5. Watching a video.** The page requests the video with a `Range` header. The
server returns `206 Partial Content` for just the requested byte range. As the
user watches, the player periodically reports the current position; the server
stores it as `last_position_seconds` against that lesson. Reopening the lesson
seeks straight back to that point.

**6. Marking a lesson complete.** The server flips that lesson's
`is_completed`. The enrolment's `progress_percent` is then recomputed as
*completed lessons ÷ total lessons × 100*. At 100% the enrolment is marked
complete with a timestamp. The user has no way to set that percentage directly.

**7. The quiz.** The user takes the quiz. The attempt and the score are
recorded. Passing is judged against the quiz's pass mark.

**8. Certificate.** On completion plus a pass, a certificate row is created
with an ID of the form `SRMS-CERT-<year>-<8 hex characters>`, generated from a
UUID. A PDF is produced with a QR code encoding the verification URL.

**9. Verification.** Anyone scans the QR. The public verification view looks
up the certificate, confirms it is genuine, shows the course and issue date,
and masks the surname. No account needed.

**10. Administrator view.** The HOD or Admin opens analytics, filtered to their
scope, and can export CSV for HR.

---

## 6. Architecture

### Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.12 (production) | — |
| Framework | Django 6.0.8 | Mature, batteries-included, strong security defaults |
| Database | PostgreSQL (production) | Referencing, constraints, concurrent writes |
| Dev/test database | SQLite | Zero-setup local runs |
| Templates | 38 server-rendered HTML | Fast on slow connections, no JS framework needed |
| Styling | Custom CSS (~2,000 lines) | No build step, no CDN dependency |
| Auth hashing | Argon2-cffi | Memory-hard |
| Rate limiting | django-ratelimit | Throttle brute force |
| PDF / QR | ReportLab, qrcode | Certificate generation |
| AI | google-genai (Gemini) | Question generation |
| Scheduling | APScheduler | Reminder jobs |
| Static files | WhiteNoise | Serve assets without a separate CDN |
| WSGI | Gunicorn | Production server |
| Hosting | Render + managed PostgreSQL | Cloud hosting |
| CI | GitHub Actions | Tests on every push |

### The four layers

**Users** — Staff, HOD, Admin. Three-tier role-based access control.

**Presentation layer** — 38 server-rendered Django templates with custom CSS.
The server returns finished HTML. There is no SPA, no client-side router, and
no front-end build step. This is a deliberate trade: less impressive on a
résumé, much better on a ₹15,000 Android phone on 3G.

**Application layer** — seven Django domain applications, each owning its
models, views, and tests:

| App | Responsibility |
|---|---|
| `users` | Accounts, roles, authentication, language preference, HR bulk enrolment |
| `courses` | Categories, courses, modules, lessons, enrolments, progress, video serving, uploads |
| `quizzes` | Quizzes, questions, attempts, Gemini-assisted generation |
| `certificates` | Issuance, PDF build, QR codes, public verification |
| `analytics` | Watch-progress report, HR dashboard, CSV export |
| `notifications` | Scheduled reminders, audit log pruning |
| `management` | Audit log, administrative operations |

**Data layer** — PostgreSQL. Content hierarchy
`Category → Course → Module → Lesson`. Progress is derived; certificates carry
a unique indexed ID.

### Two architectural decisions worth defending

**Progress is derived, never trusted.** The client never submits a percentage.
`Enrollment.recalculate()` counts completed lessons and recomputes. This is
the single decision that makes the completion record worth anything.

**Video uses HTTP Range.** Serving the whole file would make seeking download
gigabytes. Range requests make seeking an O(1) seek plus a small transfer, and
they are what makes resume-position tracking possible at all.

---

## 7. How is it tested?

**203 automated tests, run on every push and every pull request. A change
cannot land while they are red.**

### What the tests cover

| Area | Tests | What they assert |
|---|---|---|
| `users` | 54 | Login, role permissions, employee-ID validation, language preference, rate limiting, password reset, HR enrolment |
| `management` | 31 | Audit log, administrative commands, seeding behaviour |
| `courses` | 23 + 12 + 9 + 15 | Enrolment, progress recalculation, HTTP Range responses, video serving, upload validation and storage |
| `analytics` | 20 | Watch-progress rows, report scoping, CSV export |
| `quizzes` | 21 | Quiz creation, attempts, pass/fail, Gemini response parsing and malformed-input rejection |
| `certificates` | 17 | Issuance, PDF build, QR embedding, public verification, surname masking |

### The test suite is a specification, not a count

The most valuable property of this suite is not the number — it is that each of
the three security bugs below has a **regression test that fails if the bug is
ever reintroduced**. A test that encodes the vulnerability as its specification
means the fix cannot silently rot.

### The three vulnerabilities found and fixed

None were found by reading a checklist. Each was found by testing a control
against its actual attacker.

**1. Stored XSS via content-type confusion** *(commit `2382c9c`)*
Upload validation compared the declared content type and the file extension
with a logical **or**. A file named `evil.mp4` that declared `text/html`
therefore passed on its extension alone, was stored verbatim, and was later
served by the video view as `Content-Type: text/html` with
`Content-Disposition: inline` — so the browser rendered it as an HTML page.
Proven with a test that stored `<script>alert(1)</script>` as a video row.
**Fix:** both signals must now agree, and the stored type is re-derived from
the extension with `mimetypes`; the client-declared type is treated as
untrusted input. Also cleared 17 dependency advisories in the same pass.

**2. Rate-limit bypass via a client-controlled key** *(commit `6cfa3d2`)*
`get_client_ip` returned the first `X-Forwarded-For` entry. That header is set
by the *client*, and the app sits behind a proxy that *appends* to it — so the
first entry was whatever the caller chose to send. Anyone could mint a fresh
rate-limit identity per request and try passwords indefinitely.
**Fix:** the real client address is resolved from proxy-aware settings, so the
limiter keys on an address the client cannot choose.

**3. Live credentials published in a public repository** *(commit `17eeb6e`)*
The repository is public, and the README carried a full credential table —
the Super Admin, all six HODs, and the staff range — every one of which matched
the live service. Worse, the live passwords were equal to the employee IDs, so
the table was an accurate invitation.
**Fix:** all 14 accounts were given unique generated 20-character passwords,
the Render admin secret was rotated, old credentials were verified as rejected,
and the credentials now live in the macOS keychain instead of on disk.

### Dependency auditing

`pip-audit` against `requirements.txt` reports **no known vulnerabilities**.
Dependencies are pinned to exact versions, and every version bump is a commit
with a test run attached to it.

### What is *not* tested

Stated plainly, because a testing section that only lists strengths is
marketing:

- **No load or concurrency testing.** The system has not been proven at scale.
  Do not claim it has.
- **No accessibility audit** of the video player or quiz controls.
- **The Gemini integration is tested against recorded and malformed responses**,
  not against a live model on every run, so behaviour against a changed model
  version is not guaranteed.
- **Email delivery is untested end to end**, because no SMTP credentials exist.

---

## 8. Deployment

- **Hosting:** Render free web service, `https://dronav2.onrender.com`
- **Database:** externally managed PostgreSQL
- **Boot sequence:** a single `manage.py boot` step runs migrations, creates
  the cache table, and syncs the admin password, then Gunicorn starts. This was
  consolidated from three separate `manage.py` invocations because three Django
  boots dominated cold-start time on the free plan.
- **Health check:** `/health/`
- **CI/CD:** GitHub Actions runs `manage.py check`, a missing-migration check,
  the 203-test suite, `collectstatic`, and a syntax gate on every push.
  Render auto-deploys from `main` on commit.
- **Secrets:** all credentials live in the macOS keychain and Render environment
  variables — never in the repository.

### Known deployment constraints

- **Free plan, single instance.** The background scheduler is therefore
  disabled by default; enabling it on a multi-worker deployment would start a
  scheduler in every worker and double-send reminders.
- **Local-disk media storage.** Fine at this scale, but media should move to
  object storage before real load.
- **Render Blueprint has Auto Sync off.** Editing `render.yaml` does not change
  production until a sync is run deliberately.

---

## 9. Honest limitations

1. **Email is not live.** The code is complete; the SMTP credentials do not
   exist. No reminders are being sent.
2. **No load testing.** Nothing here proves behaviour under real institutional
   load.
3. **No accessibility audit** of interactive components.
4. **Two response-time figures were measured, not benchmarked.** They are
   single observations on a free-tier cold-start-prone host, not a performance
   study.
5. **Media on local disk** rather than object storage.
6. **The report's front matter, UAT responses and signatures** are authored
   material requiring verification by the team and supervisor before academic
   submission.

---

## 10. Where everything lives

| Thing | Location |
|---|---|
| **Live application** | https://dronav2.onrender.com |
| **Source repository** | https://github.com/dgexplores/DRONA |
| **Project report (Word)** | `docs/report/report3.0.docx` |
| **Project report (PDF, 51 pages)** | `docs/report/report3.0.pdf` |
| **Presentation (PowerPoint)** | `docs/presentation/finalppt.pptx` |
| **Presentation (PDF)** | `docs/presentation/finalppt.pdf` |
| **Presentation script** | `docs/presentation/SCRIPT.md` |
| **This guide** | `docs/PROJECT-GUIDE.md` |
| **38 product screenshots** | `images_project/` (see `images_project/README.md`) |
| **Engineering notes & traps** | `ENGINEERING.md` |
| **Operational handoff** | `HANDOFF.md` |
| **Roadmap / deferred work** | `ROADMAP.md` |
| **Deployment config** | `render.yaml` |
| **CI pipeline** | `.github/workflows/ci.yml` |
| **Test suite** | `apps/*/tests.py`, `apps/courses/test_*.py` |
