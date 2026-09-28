# Field Agent — Deploy Pre-Flight Checklist

Learned the hard way, September 2026. Three deploy failures, three rules.
Run this before and after every push to `main` (repo: `BAuthement/field_agent`,
live: `https://field-agent-x9z7.onrender.com`).

## The three failures

### 1. Two-worker database race (v2.1 — 2026-09-26)
**What happened:** First deploy crashed on startup.
**Cause:** Dockerfile ran Gunicorn with `--workers 2`. Both workers ran database
table creation at the same time and raced each other.
**Fix:** One worker (`--workers 1`). Fixed directly in GitHub.
**Rule:** The Dockerfile must keep exactly `--workers 1` unless database
initialization is made race-safe (a single migrate step or an advisory lock).

### 2. Dropped files in the push (v2.2 — 2026-09-27)
**What happened:** The push was reported "complete", but only 1 of 5 commits had
landed — 17 of 34 illustrations missing, the remaining commits never pushed.
**Cause:** The upload worker died mid-batch; nobody verified the full manifest
against the repo afterwards.
**Rule:** After every push, verify every expected commit appears at
`github.com/BAuthement/field_agent/commits/main` and spot-check that key files
exist in the repo tree. Never report "pushed" until the manifest matches.

### 3. Render never deployed (v2.2 — 2026-09-27)
**What happened:** All commits were on `main`, but `/health` still returned
`2.1.1` after 30+ minutes of polling.
**Cause:** Render had not started or finished a deploy — auto-deploy possibly
paused or the build stuck. Needed eyes on the Render dashboard.
**Rule:** After every push, poll `/health` until its `version` matches the
version in the pushed code (allow ~30 min for the free-tier build). If it
doesn't, check the Render dashboard's deploy events for `field-agent-x9z7`
before touching anything else.

## Pre-flight — before every push
- [ ] Dockerfile: `--workers 1` confirmed (`grep -n "workers" Dockerfile`).
- [ ] Version bumped in the `app.py` `/health` route, so the deploy can be verified.
- [ ] Full file manifest listed for the push (every file, every target path).
- [ ] Local QA suite passes (`python qa.py`).

## Post-push — after every push
- [ ] Every expected commit visible at `github.com/BAuthement/field_agent/commits/main`.
- [ ] Manifest spot-check: key files present in the repo tree (illustrations, logo, code).
- [ ] `/health` version matches the pushed version within 30 minutes.
      If not → Render dashboard → deploy events for `field-agent-x9z7`.

## Automation
`deploy_watch.py` (kept in the assistant's workspace, run every 30 min) compares
the version in `app.py` on `main` against the live `/health` version and raises
an alert if the live app trails the repo for more than 45 minutes, or if the
live app is unreachable three checks in a row. Routine in-sync checks stay silent.
