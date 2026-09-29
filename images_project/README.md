# Project Screenshots

Every user-facing interface in SRMS DRONA, captured from the live deployment at
<https://dronav2.onrender.com> on 2026-09-29.

Every image was taken by signing in as the relevant role and loading the real page — nothing here
is a mock, a wireframe, or a local database. Folder names match the role that can reach the screen.

**38 screenshots · 1440×900 at 2× (2880×1800 PNG)**

---

## `01-public/` — no sign-in required (5)

| File | Screen |
|---|---|
| `01-login.png` | Login page, with the **Staff / Trainee** and **Admin / Management** tabs |
| `02-register.png` | Self-signup, creates an inactive account pending approval |
| `03-password-reset.png` | Request a password-reset link |
| `04-404-error.png` | Custom 404 page (this one is *meant* to be a 404) |
| `05-certificate-verify-public.png` | `/verify/<id>/` — public certificate check, **surname masked** |

## `02-staff/` — signed in as `EMP001` (8)

| File | Screen |
|---|---|
| `01-dashboard.png` | Enrolled / completed / in-progress / certificates, plus available courses |
| `02-profile.png` | Personal details and preferences |
| `03-certificates.png` | Certificates earned, with download |
| `04-training-calendar.png` | Scheduled training sessions |
| `05-course-detail.png` | Course 9 — modules, lessons, per-lesson completion ticks |
| `06-lesson-video.png` | **Video lesson player** — resume position, HTTP Range seeking |
| `07-lesson-2.png` | A second lesson |
| `08-quiz.png` | Assessment screen |

## `03-hindi/` — same screens, हिन्दी (3)

| File | Screen |
|---|---|
| `01-dashboard-hi.png` | Dashboard in Hindi |
| `02-course-detail-hi.png` | Course content via the `_hi` model fields |
| `03-certificates-hi.png` | Certificates in Hindi |

These are the evidence for the bilingual claim: the **whole** interface translates — navigation,
headings, buttons, form labels, validation and error pages — not just course titles.

## `04-hod/` — signed in as `HOD_IT`, Head of Department (11)

| File | Screen |
|---|---|
| `01-hr-dashboard.png` | Department analytics: totals, average score, hours, chart |
| `02-watch-progress.png` | **Watch-progress grid** — staff × lessons, with not-started and fell-behind flags |
| `03-management-console.png` | Management console home |
| `04-mgmt-courses.png` | Course list |
| `05-mgmt-course-detail.png` | Course detail / edit surface |
| `06-mgmt-bulk-enroll.png` | Enrol a whole department |
| `07-mgmt-assign-staff.png` | Assign an individual employee |
| `08-mgmt-sessions.png` | Scheduled sessions |
| `09-mgmt-session-new.png` | Create a session |
| `10-mgmt-staff-import.png` | Import a staff roster |
| `11-ai-quiz-generator.png` | **AI quiz builder** — SOP PDF or text → MCQs via Gemini |

## `05-admin/` — signed in as `ADMIN001`, Super Admin (11)

| File | Screen |
|---|---|
| `01-management-console.png` | Management console |
| `02-certificate-directory.png` | **Certificate directory** — all staff, search + department/course filters, PDF + Verify |
| `03-hr-dashboard.png` | Analytics across all departments |
| `04-watch-progress.png` | Watch-progress across all departments |
| `05-mgmt-create-user.png` | Provision a staff or HOD account |
| `06-mgmt-course-new.png` | Create a course |
| `07-mgmt-course-edit.png` | Edit a course |
| `08-mgmt-module-edit.png` | Edit a module |
| `09-mgmt-lesson-new.png` | Upload a lesson (video or PDF) |
| `10-django-admin.png` | Django admin |
| `11-mgmt-lesson-edit.png` | Edit a lesson |

---

## Notes for whoever uses these

- **`04-hod/`, `04-hod/11` and the `03-hindi/` shots render in Hindi** because those accounts have
  `preferred_language = hi`. That is deliberate — it is the proof the bilingual layer works.
- **`01-public/04-404-error.png` is the only non-200** in the set, and that is the point: it shows
  the custom error handler.
- **Staff names and certificate IDs are real rows from the live database.** They were entered
  directly and do not appear in `seed.py`, so the repository cannot prove whether they are
  fictional test data. Treat them as public.

## Recreating these

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Then, per role, sign in and screenshot at 1440×900 with `device_scale_factor=2`.

To find IDs rather than guessing them, scrape the links off a page that lists them:

```python
JS = "() => Array.from(document.querySelectorAll('a')).map(a => a.getAttribute('href') || '').join('\\n')"
links = sorted(set(re.findall(r'/lessons/\d+/', page.evaluate(JS))))
```

Note when logging in: the page has **two** forms, so selectors must be scoped with
`form:visible input[name=...]` or Playwright will fill the hidden one and hang.

**Never commit a credential in a capture script.** Read passwords from the OS keychain or an env
var:

```bash
security find-generic-password -a EMP001 -s DRONA -w
```
