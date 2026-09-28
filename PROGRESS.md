# Field Agent — Build Progress (Milestone 1)

Project: Missionary field-agent web app for MissionaryAgents / NPL Academy.
Scope of Milestone 1: complete working codebase + local self-QA. No public deploy.

## [x] Curriculum import (2026-09-25)
- Downloaded the three NPL Academy manuals from missionaryagents.org:
  - Level 1 Seed Sower (40 pp), Level 2 Church Planter (48 pp), Level 3 Church Multiplier (58 pp)
- Parsed into `curriculum/curriculum.json`: 10 + 10 + 12 lessons, sequential,
  each with title, full body text, and Look Forward application section.
- Levels 4 (Movement Trainer) and 5 (Strategy Coordinator) listed as
  appointment-only per the Academy page.
- Attribution note included (manuals grant permission for discipleship use).

## [x] App scaffold (Flask + SQLite) (2026-09-25)
- Server-rendered Flask app, mobile-first CSS, minimal JS (assistant chat only).
- SQLite via stdlib sqlite3; DB path swappable via FIELD_AGENT_DB env (Postgres path documented in README).
## [x] Auth (register/login, per-user data isolation) (2026-09-25)
- werkzeug password hashing, session auth, all queries scoped by user_id, FK cascade.
## [x] Field work tracker (2026-09-25)
- Log/list/delete entries: 8 activity types, date, location, people count, notes, follow-up flag.
## [x] Training module (from curriculum.json) (2026-09-25)
- 5 levels (3 with full parsed lessons, 2 appointment-only), per-lesson pages,
  mark complete/incomplete, progress bars, prev/next navigation, manual PDF links.
## [x] Donor report generator (PDF) (2026-09-25)
- ReportLab PDF: profile header, stats table, highlights, full timeline, thank-you footer. Bilingual.
## [x] Built-in assistant (rule-based, bilingual) (2026-09-25)
- Quick actions (weekly summary, donor draft, quiz, log help, encourage) + free-text
  keyword intents over the user's own data. No external API keys.
## [x] Bilingual UI (EN/ES toggle) (2026-09-25)
- Full EN/ES string dictionary, header toggle, persisted per user.
## [x] Docker + one-command deploy script (2026-09-25)
- Dockerfile (gunicorn), docker-compose with persistent volume, deploy.sh (local/fly/render).
## [x] Self-QA (local run, full flow exercise) (2026-09-25)
- Ran `qa.py`: **22/22 checks pass** \u2014 register, login, log entries (2 types),
  follow-up badges, dashboard stats, training levels/lessons with real curriculum
  content, lesson completion, report PDF generation (valid PDF, verified text
  extraction incl. Spanish accents), assistant quick actions + free text (EN+ES),
  ES UI toggle, per-user data isolation, bad-login rejection, auth guards.
- **Blocker / not verifiable locally:** no Docker daemon in this VM, so
  `docker build` could not be run. Dockerfile + compose + deploy.sh are written
  per standard patterns but need a daemon-side build check in Milestone 2.

---

# Milestone 2 — Production deploy readiness + Brandon's punch list (2026-09-25)

## Hosting pick: Render (free web service) + Neon (free Postgres)

Compared as of Sep 2026 (verified via current docs/community sources):

| Platform | Free tier (2026) | Persistent volume for SQLite? | Verdict |
|---|---|---|---|
| Fly.io | None for new users since Oct 2024 (short trial, then ~$2-5/mo PAYG) | Yes, but paid | Out — not free |
| Railway | No free tier (Hobby = $5/mo base) | Paid only | Out — not free |
| Render | Yes: 512 MB RAM, 0.1 vCPU, 750 hrs/mo, sleeps after 15 min idle, no card | **No** — ephemeral disk, SQLite wiped on sleep/redeploy | App host only |
| Koyeb | Free tier exists but volumes can't attach to free instances; ephemeral | No | Out for SQLite |
| Neon (Postgres) | Free forever: 0.5 GB, 100 CU-hr/mo, autosuspends after 5 min idle and auto-wakes, no card | n/a (managed DB) | **Database pick** |

**Conclusion:** no 2026 free host offers Docker + a persistent disk for SQLite
at $0. So the app now uses **Postgres via `DATABASE_URL`** (Neon free) with
**SQLite kept as the zero-config local fallback**. Render hosts the container
for free; Neon holds the data for free. Total: $0/mo, no credit card.
`fly.toml` is included as a paid fallback (~$2-5/mo, always-on + volumes).

## [x] Postgres support via DATABASE_URL
- `db.py`: uses Postgres when `DATABASE_URL` starts with `postgres(ql)://`,
  else SQLite. App code unchanged — `?` placeholders auto-translate to `%s`,
  rows are dict-like on both backends, schema has PG (`SERIAL`) / SQLite
  (`AUTOINCREMENT`) variants.
- `requirements.txt`: added `psycopg2-binary`.

## [x] Production hardening
- `/healthz` liveness endpoint (DB check, 503 if DB unreachable); `/health` kept.
- Structured logging to stdout (`field-agent` logger, INFO); gunicorn
  `--access-logfile - --error-logfile -` in Dockerfile.
- `ProxyFix` for correct URLs/scheme behind Render/Fly proxies.
- `SESSION_COOKIE_SAMESITE=Lax`, `SESSION_COOKIE_SECURE` via `SECURE_COOKIES=1`
  (set in render.yaml/fly.toml; off for local http dev).
- Dockerfile `CMD` now honors host-injected `$PORT`.

## [x] Deploy blueprints
- `render.yaml` — Blueprint for Render free (Docker runtime, `FIELD_AGENT_SECRET`
  auto-generated, `DATABASE_URL` pasted at deploy, health check `/healthz`).
- `fly.toml` — paid fallback config (documented as such).
- `deploy.sh` + `README.md` updated for the Render+Neon path.

## [x] Brandon's punch list
- `BRANDON_PUNCHLIST.md`: 8 numbered plain-language steps (~10 min) — Neon
  account → GitHub upload → Render account → Blueprint deploy → wait for Live
  → register admin → approve launch. Each step has failure recovery.
- `~/workspace/your_files/field-agent-deploy.zip` (124K, 34 files, no venv):
  clean upload bundle for Step 1.

## [x] Self-QA (Milestone 2)
- Full `qa.py` suite: **22/22 pass on SQLite** and **22/22 pass on real
  PostgreSQL 16** (local install) — register, log, training, PDF reports,
  assistant (EN+ES), isolation, auth guards identical on both backends.
- `/healthz` returns `{"db":"postgres","ok":true}` / `{"db":"sqlite","ok":true}`
  per backend; `/health` unchanged.
- **Gunicorn boot test (2 workers): PASS** — `/healthz` 200, `/register` 200,
  access + app logs streaming to stdout.
- `render.yaml` / `fly.toml` parse and validate (yaml.safe_load / tomllib).
- **Still not verifiable locally:** `docker build` (no daemon in this VM).
  Render/Fly build the Dockerfile server-side on deploy, which covers it;
  the Dockerfile uses only standard instructions.

## Remaining for Brandon (his 10 minutes)
Per `BRANDON_PUNCHLIST.md`: create Neon account → copy connection string →
push code to GitHub → create Render account → Blueprint deploy with
`DATABASE_URL` → wait for Live → register admin account → approve launch.
No accounts created, nothing deployed, no ToS agreed — all by Brandon.

## Deploy fix (2026-09-26, evening)
- First Render deploy failed at boot: `psycopg2.errors.UniqueViolation` on
  `pg_type_typname_nsp_index`, key `(users, 2200)`. Root cause: the two
  gunicorn workers booted concurrently and both ran schema init, racing on
  `CREATE TABLE users` (every table creates a matching pg_type rowtype entry).
- Fix: single gunicorn worker (`--workers 1`) in Dockerfile — no concurrent
  DDL, race eliminated. Adequate for this app's traffic. Do NOT raise the
  worker count later without making schema init race-safe (advisory lock).
- Note: the build itself succeeded and one worker reached "Field Agent ready
  (db=postgres)" — DATABASE_URL and the Docker image are fine.

## LIVE (2026-09-26, evening)
- Brandon applied the --workers 1 Dockerfile fix via GitHub web edit (repo now
  at 2 commits). Render auto-redeployed from the new commit — deploy succeeded.
- Verified live: https://field-agent-x9z7.onrender.com serves the login page
  ("Field Agent / Missionary companion for the harvest") and /register renders
  the full registration form (name, email, password, field location).
- Remaining for Brandon: register his account, click through (log a test
  activity, open a lesson, generate a test donor report), then approve launch.

## V2 — beta flows (2026-09-27, local build; NOT deployed)
New: one-question-at-a-time quizzes (`/training/<level>/<n>/quiz`), 3 options
shuffled per question, retry-until-correct with 10 varied warm wrong-answer
notes + 10 congrats messages per language (EN/ES, no consecutive repeats),
quiz completion persisted (`quiz_done`) and enforced server-side in
`toggle_lesson`. Lesson-completed interstitial reminds the learner to do the
Look Forward homework. Homework reflection gate on entering any lesson whose
previous lesson is done: did-you-do-it? / best experience / what to improve;
"No" blocks with an obedience/application explanation and lets them retry
later; "Yes" requires both texts, shows an affirmation page, then unlocks the
lesson. Reflections persist (`homework_reflections`) and print in donor PDFs
under "Ministry experiences" / "Experiencias ministeriales" (bilingual;
works even with zero field entries). New tables: `quiz_done`,
`homework_reflections` + `idx_reflections_user`.

## V2 — workbook audit (2026-09-27; workbook is authority)
PDFs: L1 v5.0 (10 lessons), L2 v5.0 (10), L3 v6.0 (12). All 32 app lessons
matched workbook lessons; no orphans. Blank-line questions stripped from
bodies and converted to quizzes. Question counts — L1: 123 (4/13/0/31/17/16/
20/7/15/0/7), L2: 200 (37/28/17/23/13/14/14/10/26/18), L3: 181
(13/13/19/3/14/23/9/14/23/17/12/18/17). Total 504 in
`curriculum/quizzes.json`, keys exactly matching all 32 lessons. Zero
picture-only skips (every chart-adjacent answer supported by prose). Notable
fixes: L1-L10/L2-L10/L3-L12 Look Forward trimmed of exam/next-steps/closing
text that had leaked in; L2-L1 prepends orphaned "THE CHURCH" intro;
L3-L10 keeps the Brutal Impact table; OCR repairs (3-Circles, S.W.A.P.,
MAWL initials, w/ith b/oat joins); workbook typos preserved in bodies,
corrected only in quiz wording where noted.
Sources kept at `workbooks/` (PDF+txt, excluded from deploy/docker).

## V2 — QA (2026-09-27)
`qa.py`: **44/44 pass on fresh SQLite** with the real 504-question set —
quiz wrong→retry→correct, completion gate, reflection gate block/validate/
affirm, PDF with reflection text, ES quiz/feedback/completion, isolation,
auth guards. v1→v2 migration on a true v1-schema DB: old users/entries/
progress intact, new tables created empty, `init_db()` idempotent. ES donor
PDF verified via pdftotext ("Experiencias ministeriales", reflection text).
Known limitation: lesson titles stay English in ES mode (matches the rest of
the app; translating 32 curriculum titles is Brandon's call).
Deploy bundle rebuilt: `~/workspace/your_files/field-agent-deploy.zip`
(35 files incl. `curriculum/quizzes.json` + 3 new templates; no venv,
no workbooks).
Exam counts verified from workbooks: L1 oral demo = 30 items (5 tools × 6;
90s/5min/5min/2min/5min limits); L2 = 31 printed items (Church Circle prints
7 despite "six parts" intro); L3 = 22 requirements (1+3+4+3+3+3+2+3;
workbook mislabels T5/T6). `EXAM_PROPOSAL_DRAFT.md` corrected 19→22.

## V2.1 — level-entry hard gate (2026-09-27; Brandon's ruling: prerequisites are hard gates, self-reported)
Workbook-verified prerequisite lists (verbatim source, typos fixed in app
wording, e.g. "3-Cirlces"→"3-Circles"):
- Enter Level 2 (from L1 "Before Taking Level 2 Training, You Must:", p.37):
  1) led at least one person to Christ; 2) started at least one House of
  Peace; 3) meeting several people at the House of Peace weekly;
  4) sharing Testimony and/or 3-Circles at the weekly meetings;
  5) sharing a different Story of Hope at each weekly meeting.
- Enter Level 3 (from L2 "Before Taking Level 3 Training, You Must:", p.45):
  1) baptized at least one believer led to Christ; 2) served communion to
  disciples at a House of Peace; 3) taken disciples into the harvest several
  weeks; 4) taught at least three 3/3 discipleship groups;
  5) turned at least one House of Peace into a church.
- Stored in `curriculum/gates.json` (keys "2","3"; each item {en, es}).
  L3's "Before Level 4" list exists in the workbook but is NOT gated —
  Levels 4–5 stay appointment-only per spec.
Flow: entering Level 2/3 (level page, lesson pages, quiz, lesson toggle —
all guarded against deep links) while unattested → `/training/<level>/gate`.
Gate shows "finish your lessons first" until every lesson of the previous
level is complete; then the checklist: all 5 items + honesty affirmation
("I confirm before God that I have truly done each of these") required to
submit. Attestation recorded in new `level_gates(user_id, level_id,
attested_at)` table (PK on user+level; per-user isolation; init_db creates
it; v1-schema migration verified — old users/progress intact). Bilingual
EN/ES throughout. `/health` now returns `{"ok": true, "version": "2.1"}`.
New template `templates/level_gate.html`. Dockerfile untouched (--workers 1).
Not built (awaiting Brandon's approval): trainer-attested exam checklists,
graduate-register export.
## V2.1 — QA (2026-09-27)
`qa.py`: **60/60 pass on fresh SQLite** — 44 carried v1/v2 checks + 16 new:
health version 2.1; level2 blocked pre-lessons; lesson deep-link blocked;
premature attestation (checklist POST with incomplete lessons) rejected;
checklist appears only after all 10 L1 lessons; partial attestation
rejected and still blocked; full attestation unlocks level + lesson
(composes correctly with the homework reflection gate on L2-L1);
L3 gate lessons-first; revisiting gate redirects into level; per-user
isolation; ES checklist + lessons-first render; v1→v2.1 migration creates
level_gates and preserves users/progress.
Deploy bundle rebuilt: `~/workspace/your_files/field-agent-deploy.zip`
(37 files: 35 v2 files + `curriculum/gates.json` + `templates/level_gate.html`).

## V2.1.1 — label fix (2026-09-27)
Live beta walkthrough as "Mark Z." caught a text bug on the level-entry gate
page: "Level Level 2: Church Planter" (doubled "Level"). Cause:
`curriculum.json` level `number` is already "Level 2", and app.py prepended
another "Level ". Fixed `level_label`/`prev_label` in the gate view to use the
number as-is. Also bumped /health to 2.1.1 for deploy detection. The reported
header-"Logout" quirk was a test misclick on the ES language toggle (no header
logout link exists; Profile → Log out works). Donor-report "Ministry
experiences" section verified in local QA via pdftotext (60/60); live PDF
binary could not be read by the browser task.

## V2.2 (deployment in progress, 2026-09-27) — lesson illustrations + MissionaryAgents branding + experience tracking
Two owner requests shipped together, plus a third added before release.

**Illustrations.** Every training lesson page now shows its workbook diagram
illustration(s) as the drawing model ("Example illustration — draw yours like
this"), addressing the owner's note that students had no visual example to
draw from.
- 34 PNGs extracted from the three workbooks into static/img/illustrations/
  (each >=800px wide, <250KB, 4.2MB total), mapped in
  curriculum/illustrations.json keyed by "levelN:M".
- 8 lessons have no workbook diagram and map to [] (nothing invented):
  L1:2 S.W.A.P., L1:9 Prayer For Salvation, L1:10 Affirm,
  L3:2 Spiritual Leadership, L3:7 Tools, L3:9 Training,
  L3:11 Troubleshooting, L3:12 Treasure.
- Wiring: curriculum.get_lesson_illustrations(), illustration context in the
  lesson view, <figure> block in templates/training_lesson.html, EN/ES strings
  (illus_title/illus_sub).

**Branding.** Whole app now wears the MissionaryAgents brand from
missionaryagents.org (dark navy + gold field-ops theme, real logo):
- static/img/ma-logo.png (official MA_Logo_Full.png, resized 640px, transparent).
- Header topbar: navy with gold underline + logo + "Field Agent"; login page:
  navy logo band; tabs navy; buttons gold; headings navy.
- Donor-report PDF: navy logo band at top, navy/gold palette throughout,
  verified with embedded logo via pypdf.

- /health version bumped 2.1.1 -> 2.2. qa.py version assertion updated.
- Verification: 135/135 illustration checks, full QA 71/71 on clean local DB,
  PDF logo-band check. Live deploy NOT yet verified — GitHub upload stalled
  after the first illustration batch; remaining files deploy next.

**Experience tracking (added 2026-09-27, before v2.2 release).** When a
homework reflection describes ministry action ("I shared my testimony with 3
people", "we drew the 3-Circles", "Compartí mi testimonio con cuatro
personas"), the app now identifies the wording, maps it to an activity type
(testimony/3-Circles/gospel -> gospel_conversation; also 3/3, baptism,
prayer, training, church planting), and auto-logs an activity entry so it is
counted on the dashboard and in the donor report without re-entry.
- New module experience.py: keyword patterns (EN/ES) + people-count extraction
  (digits and word-numbers, one optional adjective, "with N" fallback).
- If no count is found in the text, the affirmation page asks "How many people
  did you share with?" (new /training/<level>/<n>/count route); the saved
  number lands on the entry.
- entries gains source ('manual'/'reflection') and reflection_id columns via
  init_db migration (works on the live Postgres DB too); dashboard and log
  show a "From your reflection" badge on auto entries; editing a reflection
  updates the linked entry instead of duplicating it.
- QA: 11 new checks (EN testimony+count, 3-Circles ask-and-save, ES testimony,
  blocked->affirmed, baptism, no false positive on plain study text).
