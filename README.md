# Field Agent

Missionary field companion for **MissionaryAgents / NoPlaceLeft Academy**.
Missionaries log their field work, train in the real NPL Academy curriculum,
generate donor-report PDFs, and get help from a built-in assistant \u2014 in
English or Spanish, from any phone browser.

## Features

- **Field work tracker** \u2014 log gospel conversations, discipleship meetings,
  training sessions, church-plant activities, baptisms, prayer, humanitarian aid;
  with dates, locations, people reached, notes, and follow-up flags.
- **Training** \u2014 the actual NoPlaceLeft Academy curriculum (Five Levels of
  Leadership). Levels 1\u20133 ship with full lesson content parsed from Brandon's
  training manuals; Levels 4\u20135 are marked appointment-only per the Academy.
- **Donor reports** \u2014 one click generates a polished PDF (stats, highlights,
  timeline, missionary profile) for any date range.
- **Built-in assistant** \u2014 rule-based, works offline over the missionary's own
  data: weekly/monthly summaries, donor-letter drafts, training quizzes, logging
  help, follow-up lists, encouragement. No AI API keys needed.
- **Bilingual UI** \u2014 full English/Spanish toggle, persisted per user.
- **Multi-user** \u2014 register/login; every missionary sees only their own data.

## Run locally

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py        # http://localhost:5000
```

Or with Docker:

```bash
./deploy.sh                     # one command: builds + starts on :5000
```

Free-tier hosting notes: `./deploy.sh render` prints the recommended $0/mo path
(Render free web service + Neon free Postgres). A `fly.toml` fallback is also
included, but Fly.io has no free tier for new accounts (trial only, then paid).

## Configuration

| Env var              | Default                  | Purpose                                                        |
|----------------------|--------------------------|----------------------------------------------------------------|
| `DATABASE_URL`       | *(unset → SQLite)*       | Postgres connection string (e.g. Neon). When set, the app uses Postgres |
| `FIELD_AGENT_DB`     | `./data/field-agent.db`  | SQLite path (used only when `DATABASE_URL` is unset)           |
| `FIELD_AGENT_SECRET` | `dev-secret-change-me`   | Flask session secret \u2014 **set in production**              |
| `SECURE_COOKIES`     | *(unset)*                | Set to `1` in production (HTTPS-only session cookies)          |
| `PORT`               | `5000`                   | Listen port (Render/Fly inject their own)                      |

## Layout

```
app.py            routes + auth
db.py             SQLite schema/helpers
i18n.py           EN/ES strings
curriculum.py     curriculum loader
curriculum/       curriculum.json (parsed from the three NPL manuals)
assistant.py      rule-based assistant engine
reports.py        ReportLab donor-report PDFs
templates/        server-rendered pages (mobile-first)
static/style.css  stylesheet
qa.py             end-to-end self-QA script (22 checks)
```

## Curriculum source

Lessons are parsed from the official NPL Academy manuals at missionaryagents.org
(Level 1 Seed Sower, Level 2 Church Planter, Level 3 Church Multiplier).
The manuals grant permission for discipleship use; attribution is shown in-app.
