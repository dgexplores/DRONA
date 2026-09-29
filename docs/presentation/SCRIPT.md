# SRMS Drona — Presentation Script

**Deck:** `docs/presentation/finalppt.pptx` (10 slides)
**Target length:** 10–12 minutes
**Live demo URL:** https://dronav2.onrender.com

> How to use this: the text under **Say** is what you speak. Lines marked
> *(optional)* can be dropped if you are running short. Every number in this
> script was checked against the codebase on the date of the commit — do not
> add numbers that are not here.

---

## Timing at a glance

| Slide | Topic | Time | Running |
|---|---|---|---|
| 1 | Title | 0:30 | 0:30 |
| 2 | Problem & Real-World Need | 1:00 | 1:30 |
| 3 | Our Proposed Solution | 1:15 | 2:45 |
| 4 | How Our Solution Works | 1:00 | 3:45 |
| 5 | Key Innovations & USP | 1:00 | 4:45 |
| 6 | System Architecture | 1:30 | 6:15 |
| 7 | AI-Assisted Assessment Generation | 1:00 | 7:15 |
| 8 | Feasibility, Impact & Deployment | 1:15 | 8:30 |
| 9 | Why Our Solution? | 0:45 | 9:15 |
| 10 | Thank You | 0:15 | 9:30 |

Leaves ~2–3 minutes for questions.

---

## Slide 1 — Title (0:30)

**Say:**

> Good morning. We are group [team], and our project is **SRMS Drona** — a
> learning web application for the non-teaching staff of SRMS. It is our
> internship project, guided by Ms. Sakshi Goel of the Department of IT.
>
> In the next ten minutes we will show you the problem we set out to solve,
> what we built, how it is architected, and how we verified it works.

*(optional)* One line of context that helps the room: "The audience for this
system is not students. It is the college's own clerical, administrative and
support staff."

---

## Slide 2 — Problem & Real-World Need (1:00)

**Say:**

> Let's start with why this problem exists.
>
> Training material for non-teaching staff in an institution usually lives in
> three bad places at once: shared drives nobody opens, printed notes that go
> out of date, and WhatsApp forwards. That means the material is hard to reach,
> hard to update, and there is no record of who actually completed it.
>
> Four concrete gaps:
>
> **One —** training resources have no single, central place to live.
> **Two —** the material is not easy to reach on a phone, and most of our staff
> are on mobile more than they are at a desk.
> **Three —** there is no structured way to deliver a course and then check
> whether it was actually learned.
> **Four —** administrators have no tool to see who has done what.
>
> Notice the last one is the important one. Collecting a signature is not the
> same as recording completion. We wanted a system where completion is a fact
> the system derives, not a claim someone types in.

---

## Slide 3 — Our Proposed Solution (1:15)

**Say:**

> SRMS Drona is our answer to that. Seven capabilities:
>
> **Staff Learning** — a personal dashboard where each person sees the courses
> assigned to them, in one place.
>
> **Course Management** — content is structured as Category, then Course, then
> Module, then Lesson. That structure is what lets progress be computed rather
> than guessed.
>
> **Quiz Management** — digital assessments attached to a course.
>
> **Progress Tracking** — this is the core one. Progress is calculated on the
> server from which lessons are actually complete. The browser never sends
> "I am 80% done". I will show you why that matters on the architecture slide.
>
> **Certificate Generation** — when someone completes a course and passes its
> assessment, a certificate is issued with a QR code.
>
> **Notifications** — a scheduled job can remind staff with incomplete
> mandatory training. *(optional — see the honesty note below.)*
>
> **Role-Based Administration** — three roles: staff, Head of Department, and
> Super Admin. Each sees a different console.

**Honesty note on notifications — say this if asked:** the reminder scheduler
and the email code are fully implemented, but email delivery is switched off
until the institute provides SMTP credentials, and the scheduler is disabled by
default so it does not start in every web worker. So: the feature is built, the
mail server is not connected yet. Do not claim reminders are currently being
emailed.

---

## Slide 4 — How Our Solution Works (1:00)

**Say:**

> This is the journey of one person, start to finish.
>
> They log in with their **employee ID** and password — not an email address.
> Staff are enrolled in courses by their department. They open the learning
> content, and if it is a video, the player remembers exactly where they
> stopped, so they resume rather than restart.
>
> They take a **digital quiz**. When they pass and finish every lesson, the
> system issues a **certificate with a QR code**. The QR code opens a public
> verification page — no login needed — so an employer or a verifier can check
> a certificate without needing an account.
>
> The loop to emphasise: content, assessment, and proof of completion are all in
> the same system. Nothing has to be reconciled by hand afterwards.

---

## Slide 5 — Key Innovations & USP (1:00)

**Say:**

> Why is this not just another generic LMS? Four things make it specific to us.
>
> **Institution specific.** The content model, the roles, and the vocabulary are
> built for an institution's internal staff training — not for selling courses
> to the public.
>
> **Simple interface.** 38 server-rendered pages, custom CSS, no build step and
> no JavaScript framework. That is a deliberate choice: it loads fast on a
> mid-range phone, which is where most of our users will be.
>
> **Hindi and English.** The entire interface is bilingual — 401 translated
> interface strings — plus bilingual fields for course content, so a course can
> exist in both languages at once. This is not a machine translation; it is
> maintained by hand.
>
> **Role-based access control.** Three tiers, enforced on the server, not just
> hidden in the menu.
>
> And it is **all in one** — learning, quizzes, certificates and reporting —
> rather than four tools that have to be reconciled.

---

## Slide 6 — System Architecture (1:30)

**Say:**

> This is the part we most want to defend, so let us take it layer by layer.
>
> **Built on Django 6.0.8 and Python 3.12, with PostgreSQL in production.**
> Both are mature, well-documented, and widely supported — which matters for a
> system that has to keep running after we have graduated.
>
> **The presentation layer** is 38 server-rendered HTML templates with custom
> CSS. The server sends finished pages, so the app works even on a slow
> connection, and there is no separate front-end application to deploy.
>
> **The application layer is seven domain applications** — users, courses,
> quizzes, certificates, analytics, notifications, and management. Each owns
> its own models and views. We deliberately did not write one large module; the
> boundaries are what make the test suite possible.
>
> Two security decisions belong here:
> **Passwords are hashed with Argon2** — a memory-hard algorithm, so a stolen
> database does not hand over usable passwords.
> **Sessions are server-side**, so signing out actually invalidates the
> session.
>
> **The data layer** is PostgreSQL. Content is a four-level hierarchy —
> Category, Course, Module, Lesson. Progress and certificates are derived and
> uniquely identified on the server.
>
> Three engineering details along the bottom that we are happy to be judged on:
> **203 automated tests**, green on every push. **Zero known dependency
> advisories**, checked by an automated audit. And **three real vulnerabilities
> that we found and fixed ourselves** — I will come back to those.
>
> One implementation detail worth calling out, because it was a deliberate
> decision: **video is served over HTTP Range requests.** That is what makes
> seeking instant and what lets us store and resume a watch position, without
> downloading the whole file.

---

## Slide 7 — AI-Assisted Assessment Generation (1:00)

**Say:**

> This is the part that saves an administrator the most time.
>
> Writing quiz questions by hand is slow. So an administrator uploads an SOP
> document — a standard operating procedure, an institute policy, a circular —
> or pastes text directly. **Google Gemini** then generates multiple-choice
> questions with answer keys and explanations.
>
> Two things we were deliberate about.
>
> First, the model is a helper, not an authority. **A generated quiz is never
> published automatically.** The administrator reviews and edits every
> question before it reaches a learner. In the screenshot you can see a real
> generated question with its options.
>
> Second, the code handles the ways models actually fail. The model wraps its
> JSON in markdown fences, it sometimes returns malformed data, and it retires
> model versions without warning. So the parser strips the fences, every item
> is validated before it can reach the database, and there is a fallback chain
> across model versions. If Gemini is unavailable, the feature degrades
> visibly instead of silently producing a broken quiz.

---

## Slide 8 — Feasibility, Impact & Deployment (1:15)

**Say:**

> **Feasibility.** We deliberately chose boring, well-documented technology —
> Django and PostgreSQL. The design is modular, so a feature can be changed
> without rewriting the system. And it runs with SQLite locally and in tests, so
> any developer can run the whole thing on a laptop with one command and no
> database server.
>
> **Impact.** Digital staff training, one-click access to resources, progress
> and achievement tracking that is derived rather than self-reported, and
> digital certificates that can be verified by anyone with a QR scan.
>
> **Deployed and verified** — and this is the part we would like you to check
> rather than take on trust:
>
> The system is **live on cloud hosting** at `dronav2.onrender.com`, with
> **continuous integration on every push** — the 203-test suite runs before any
> change can land. A dependency audit reports **zero known advisories**.
>
> And we found **three real vulnerabilities by attacking our own system**, and
> fixed all three. They are worth naming because they show how we worked:
>
> **One — a stored XSS.** Our upload validation checked the declared file type
> and the file extension with an *or*. So a file could pass on its extension
> while its content type said HTML, and the browser would render it as a page.
> The fix: both signals must agree, and the stored type is re-derived from the
> extension.
> **Two — a rate-limit bypass.** Our rate limiter keyed on the first
> `X-Forwarded-For` entry. That header is set by the *client*, so anyone could
> mint a fresh identity per request and try passwords indefinitely.
> **Three — live credentials published in a public repository.** Our README
> listed real account credentials, and worse, the live passwords were equal to
> the employee IDs. All fourteen accounts were given unique generated
> passwords, and the credentials now live in the macOS keychain instead of in
> the repository.
>
> The common thread: none of these were found by reading a checklist. Each was
> found by testing a control against an actual attacker.

---

## Slide 9 — Why Our Solution? (0:45)

**Say:**

> To summarise the difference concretely.
>
> A generic LMS is built for a general audience, gives a standard experience,
> is usually single-language, splits administration across separate tools, and
> has generic permissions.
>
> Ours is SRMS specific, works on mobile, is Hindi and English in the *same*
> interface, keeps everything in one place, and has three real permission tiers.
>
> The screenshot is the dashboard running in Hindi. It is the same application
> and the same build as the English one — we did not write a second app. The
> user simply switches language, and their choice is stored on their account.

---

## Slide 10 — Thank You (0:15)

**Say:**

> That is SRMS Drona — live, tested, and open source. The repository, the full
> project report, and all thirty-eight product screenshots are linked below.
> We are happy to take questions.

---

## Likely questions, with honest answers

**"Is it actually deployed, or is it just on your laptop?"**
Live at https://dronav2.onrender.com — the login page and health endpoint are
publicly reachable. The source is on GitHub and every push runs the 203-test
suite.

**"How do you know the tests are real?"**
They run on every push in CI and a push cannot land while they are red. The
suite covers authentication, role permissions, video range responses, upload
validation, quiz generation, certificate generation, and analytics. The three
vulnerabilities we mentioned each have a regression test that fails if the bug
is ever reintroduced.

**"Why Django instead of React or a Node backend?"**
Because the users are on mobile, often on poor connections, and not all of them
have fast devices. Server-rendered pages are smaller, work without JavaScript,
and there is no front-end build to deploy. We would rather spend the effort on
bilingual content and access control.

**"What happens if Gemini is down?"**
Quiz generation is the only feature that needs it. Everything else is
unaffected, and the generator falls back across model versions and reports
visibly when it has degraded rather than writing a broken quiz.

**"Could a staff member see another person's results?"**
No. Permissions are enforced on the server on every view, not just by hiding
menu items. A staff member sees only their own enrolments; a Head of
Department sees their department; only a Super Admin sees the whole platform.
There are tests for exactly this.

**"How do you handle a lost password?"**
There is a reset flow, it is rate-limited separately from login, and it does
not reveal whether an account exists.

**"What is not finished?"**
Be honest and say it plainly. Email delivery is not connected — the code is
there but the institute has not issued SMTP credentials, so no reminders are
actually being sent yet. The background scheduler is off by default for the
same reason. Object storage is still local disk rather than S3, and there has
been no load or concurrency testing, so do not claim the system has been
proven at scale.

**"What would you do next?"**
Connect SMTP so the reminder feature actually runs, move media to object
storage, add an accessibility pass on the video player and quiz controls, and
run a load test before the institute commits to real training deadlines.
