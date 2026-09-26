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
