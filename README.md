# SRMS DRONA — Staff Learning & Training Platform

A training portal for the **non-teaching staff** of SRMS Group of Institutions. Staff watch
short SOP videos, take quizzes, earn QR-verifiable certificates, and see what training is still
pending. Their Head of Department and the Super Admin build courses and track progress.

| | |
|---|---|
| **Live app** | <https://dronav2.onrender.com> |
| **Sign in** | <https://dronav2.onrender.com/login/> |
| **Source** | <https://github.com/dgexplores/DRONA> |
| **Stack** | Django 6.0.8 · Python 3.12 · PostgreSQL · server-rendered HTML |
| **Tests** | 203 passing, green on every push |
| **Dependencies** | 0 known vulnerabilities (`pip-audit`) |

```bash
git clone https://github.com/dgexplores/DRONA.git && cd DRONA
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./venv/bin/python manage.py migrate && ./venv/bin/python seed.py
./venv/bin/python manage.py runserver        # http://127.0.0.1:8000/
```

The Hindi translation catalog is committed, so a fresh clone runs without `gettext` installed.

---

## What it does

**For staff** — a bilingual (English / हिन्दी) learning app. Assigned courses, video lessons that
resume where you stopped, quizzes with a 70% pass threshold and retries, certificates you can
download, and an installable PWA. No tracking, no lockout, no dead ends.

**For HODs** — a management console: create courses, upload lessons, schedule sessions on an
editable calendar, enrol people by department or individually, approve new sign-ups, and run HR
analytics including a per-lesson **watch-progress report** with CSV export.

**For the Super Admin** — everything an HOD can do, plus creating HOD accounts and a
platform-wide certificate directory with search and filters.

### Three things worth a closer look

- **Progress cannot be forged.** Watch position is saved on a 10s heartbeat, and lesson
  completion is **derived server-side** from accumulated watch time (90% of duration). A
  forged `completed: true` from the browser console earns nothing.
- **Three real vulnerabilities were found by testing each control against its attacker** — a
  stored XSS on media routes, missing security headers on exactly the routes that echo uploader
  bytes, and a rate limiter that was trivially bypassable via a client-controlled header. All
  three are fixed, and each fix has a regression test. Details:
  [`ENGINEERING.md`](ENGINEERING.md).
- **Production refuses to boot misconfigured.** With `DJANGO_DEBUG=False`, the settings module
  raises on a default `DJANGO_SECRET_KEY` and on `ALLOWED_HOSTS=*` rather than serving wide open.

---

## Try it

**Live** — sign in at [`/login/`](https://dronav2.onrender.com/login/). The live site is
**locked down**: all 14 accounts have unique generated 20-character passwords, none published
here. Employee IDs below are public identifiers, not secrets.

| Role | Employee ID | Password |
|---|---|---|
| Super Admin | `ADMIN001` | *(held in the Render env var)* |
| Head of Department | `HOD_IT` `HOD_CS` `HOD_EN` `HOD_EE` `HOD_PHARM` `HOD_MGMT` | *(unique, not published)* |
| Staff | `EMP001` … `EMP006`, `EMP010` | *(unique, not published)* |

> A fresh **local** `seed.py` uses published defaults (`ADMIN001`/`ADMIN001`, HOD = its own ID,
> staff = `drona123`). Those match no live account.

**Walkthrough paths**

| | |
|---|---|
| Course 9 — Workplace Communication & Conduct | [`/courses/9/`](https://dronav2.onrender.com/courses/9/) |
| HR dashboard | [`/analytics`](https://dronav2.onrender.com/analytics) |
| Watch-progress report | [`/analytics/watch-progress/`](https://dronav2.onrender.com/analytics/watch-progress/) |
| Certificate verification | [`/verify/<id>/`](https://dronav2.onrender.com/verify/) |

> **Login is rate-limited to 5 attempts / 5 minutes per IP** — fine for one tester, a wall for a
> group demo. Tell us if you need it loosened.

---

## Architecture notes

Only the parts that shape decisions. Full detail in [`ENGINEERING.md`](ENGINEERING.md).

- **Auth is employee ID + password only.** Three roles: `staff` → `hod` → `admin`. Third-party
  SSO (Clerk) was integrated, then removed — the integration shipped two real defects and is
  documented so a future re-add is deliberate.
- **Video lives in the database**, served with HTTP Range support so seeking works. Moving it to
  object storage is a known future step, not an oversight.
- **AI quiz generation** turns an SOP PDF into MCQs with answer keys. When the API is
  unavailable the rule-based generator runs and **a warning is logged** — template questions are
  never presented as AI-generated.
- **`render.yaml` is Blueprint-authoritative but Auto Sync is OFF.** Config changes need a
  dashboard Sync. Editing the file alone does nothing. This caused one incident and is now
  documented as a trap.
- **Email is not live.** The reminder scheduler runs, but no SMTP credentials are set, so mail
  logs a `WARNING` instead of pretending to send. Deliverability work is the one piece of
  go-live left.

---

## Operating it

- **Status log** — [`HANDOFF.md`](HANDOFF.md): deploy state, outstanding work, how to verify.
- **Planned work** — [`ROADMAP.md`](ROADMAP.md): YouTube-hosted lessons, why Google Drive links
  cannot be position-tracked, when video should leave the database. Agreed, deliberately unbuilt.
- **Render service** — `srv-dajkh37qj5pc73e038i0`, Blueprint `exs-daq0qoek1f9s73dhte70`.
  Config in [`render.yaml`](render.yaml); secrets live only in Render env vars and are
  **write-only**, so a password manager is the source of truth for them.
- **Admin password rotation** — the Render start command runs `manage.py boot`, which applies
  `DJANGO_ADMIN_PASSWORD` **on every deploy**. Change the env var *and* the database together, in
  that order, or the next deploy reverts one of them.
- **Demo mode** — `reset_test_passwords` restores `password == employee ID` for a walkthrough.
  It requires a typed confirmation, can be narrowed with `--role`, and **republishes every
  account it touches.** Treat it as a temporary switch, never a convenience.
- **CI/CD** — GitHub Actions runs the Django check, a missing-migration check, the full 203-test
  suite, `collectstatic` and `compileall` on every push and PR. Backend deploys to Render on push
  to `main`; a 5-minute cron pings `/health/` so the free instance stays warm.

---

## Development

```bash
./venv/bin/python manage.py test apps --settings=srms_dorna.test_settings
```

The suite covers auth, RBAC, the approval flow, rate limiting, quizzes, certificates, the
certificate directory, per-student assignment, calendar gating and analytics — plus a named
regression test for every defect fixed in `ENGINEERING.md`. Tests write generated PDFs to a
temporary directory, so a run leaves the working tree clean.

**Before changing how the system behaves, read [`ENGINEERING.md`](ENGINEERING.md).** It records
the invariants this project depends on and the traps it has already hit.

---

## License & usage

Internal educational project for SRMS Group of Institutions. Not for redistribution without
permission.
