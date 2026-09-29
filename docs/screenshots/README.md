# Screenshots

Captured from the live deployment at <https://dronav2.onrender.com> on 2026-09-29, by signing in
as each role and walking the real pages — not mocks or a local database.

| File | Role | Screen |
|---|---|---|
| `01-login.png` | — | Login page, with the Staff and Admin/Management tabs |
| `02-staff-dashboard.png` | Staff | Dashboard: enrolled / completed / in-progress / certificates, plus available courses |
| `03-course-catalog.png` | Staff | Course catalogue |
| `04-course-9-lesson.png` | Staff | Course 9, module and lesson list with per-lesson completion ticks |
| `05-watch-progress-report.png` | HOD | Watch-progress grid, staff × lessons, **in Hindi** |
| `06-hr-dashboard.png` | HOD | HR analytics: totals, average score, total hours, department chart — **in Hindi** |
| `07-certificate-directory.png` | Admin | Certificate directory with search, department and course filters |

Notes:

- `05` and `06` are in Hindi because that account's language preference is `hi` — they are the
  evidence for the bilingual claim, not an accident.
- Staff names and certificate IDs are real rows from the live database.

## Recreating

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Then sign in per role and screenshot at 1440×900, `device_scale_factor=2`. The files here are
2880×1800. Do not commit credentials in a script; read them from a keychain or env var.
