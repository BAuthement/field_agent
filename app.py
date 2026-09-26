"""Field Agent \u2014 missionary field companion for MissionaryAgents / NPL Academy."""
import logging
import os
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, jsonify, redirect, render_template, request, Response,
                   session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import db
from assistant import answer as assistant_answer
from curriculum import get_curriculum, get_lesson, get_level, next_lesson_for
from i18n import STRINGS, get_lang, t
from reports import generate_report

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("field-agent")

ENTRY_TYPES = ["gospel_conversation", "discipleship_meeting", "training_session",
               "church_plant", "baptism", "prayer", "humanitarian", "other"]

app = Flask(__name__)
# Behind Render/Fly's reverse proxy: honor X-Forwarded-* for correct URLs/scheme.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.environ.get("FIELD_AGENT_SECRET", "dev-secret-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("SECURE_COOKIES") == "1":
    # Production behind HTTPS only; keep off for local http dev.
    app.config["SESSION_COOKIE_SECURE"] = True


@app.context_processor
def inject_i18n():
    lang = get_lang(session)
    return {"t": lambda k, **kw: t(k, lang, **kw), "lang": lang, "STRINGS": STRINGS}


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def current_user():
    conn = db.get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_entries(user_id):
    conn = db.get_db()
    rows = conn.execute("SELECT * FROM entries WHERE user_id = ? ORDER BY date DESC, id DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def user_progress(user_id):
    conn = db.get_db()
    rows = conn.execute("SELECT level_id, lesson_number FROM progress WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return {(r["level_id"], r["lesson_number"]) for r in rows}


@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/lang/<code>")
def set_lang(code):
    if code in ("en", "es"):
        session["lang"] = code
        conn = db.get_db()
        if "user_id" in session:
            conn.execute("UPDATE users SET language = ? WHERE id = ?", (code, session["user_id"]))
            conn.commit()
        conn.close()
    return redirect(request.referrer or url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        location = request.form.get("field_location", "").strip()
        if not name or not email or not password:
            return render_template("register.html", error=t("form_error", get_lang(session)))
        conn = db.get_db()
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            conn.close()
            return render_template("register.html", error=t("register_error_exists", get_lang(session)))
        conn.execute(
            "INSERT INTO users (name, email, password_hash, field_location, language, created_at) VALUES (?,?,?,?,?,?)",
            (name, email, generate_password_hash(password), location, get_lang(session), db.now_iso()))
        conn.commit()
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
        conn.close()
        session["user_id"] = user_id
        return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = db.get_db()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["id"]
            session["lang"] = row["language"] or "en"
            return redirect(url_for("dashboard"))
        return render_template("login.html", error=t("login_error", get_lang(session)))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    entries = user_entries(user["id"])
    progress = user_progress(user["id"])
    stats = {
        "activities": len(entries),
        "people": sum(e["people_count"] or 0 for e in entries),
        "baptisms": sum(1 for e in entries if e["type"] == "baptism"),
        "churches": sum(1 for e in entries if e["type"] == "church_plant"),
        "lessons": len(progress),
        "followups": sum(1 for e in entries if e["follow_up"]),
    }
    return render_template("dashboard.html", user=user, stats=stats, recent=entries[:8])


@app.route("/log", methods=["GET", "POST"])
@login_required
def log_work():
    user = current_user()
    if request.method == "POST":
        etype = request.form.get("type", "other")
        if etype not in ENTRY_TYPES:
            etype = "other"
        edate = request.form.get("date") or date.today().isoformat()
        try:
            people = int(request.form.get("people_count") or 0)
        except ValueError:
            people = 0
        conn = db.get_db()
        conn.execute(
            "INSERT INTO entries (user_id, type, date, location, people_count, notes, follow_up, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (user["id"], etype, edate, request.form.get("location", "").strip(),
             people, request.form.get("notes", "").strip(),
             1 if request.form.get("follow_up") else 0, db.now_iso()))
        conn.commit()
        conn.close()
        return redirect(url_for("log_work", saved=1))
    entries = user_entries(user["id"])
    return render_template("log.html", entries=entries, types=ENTRY_TYPES,
                           today=date.today().isoformat(), saved=request.args.get("saved"))


@app.route("/log/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_entry(entry_id):
    conn = db.get_db()
    conn.execute("DELETE FROM entries WHERE id = ? AND user_id = ?", (entry_id, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("log_work", deleted=1))


@app.route("/training")
@login_required
def training():
    progress = user_progress(session["user_id"])
    levels = []
    for lvl in get_curriculum()["levels"]:
        done = sum(1 for les in lvl["lessons"] if (lvl["id"], les["number"]) in progress)
        levels.append({"level": lvl, "done": done})
    return render_template("training.html", levels=levels)


@app.route("/training/<level_id>")
@login_required
def training_level(level_id):
    lvl = get_level(level_id)
    if not lvl or not lvl["lessons"]:
        return redirect(url_for("training"))
    progress = user_progress(session["user_id"])
    lessons = [{"lesson": les, "done": (level_id, les["number"]) in progress} for les in lvl["lessons"]]
    return render_template("training_level.html", level=lvl, lessons=lessons)


@app.route("/training/<level_id>/<int:number>")
@login_required
def training_lesson(level_id, number):
    lvl = get_level(level_id)
    les = get_lesson(level_id, number)
    if not lvl or not les:
        return redirect(url_for("training"))
    progress = user_progress(session["user_id"])
    done = (level_id, number) in progress
    total = len(lvl["lessons"])
    prev_n = number - 1 if number > 1 else None
    next_n = number + 1 if number < total else None
    return render_template("training_lesson.html", level=lvl, lesson=les, done=done,
                           total=total, prev_n=prev_n, next_n=next_n)


@app.route("/training/<level_id>/<int:number>/toggle", methods=["POST"])
@login_required
def toggle_lesson(level_id, number):
    conn = db.get_db()
    exists = conn.execute(
        "SELECT 1 FROM progress WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
        (session["user_id"], level_id, number)).fetchone()
    if exists:
        conn.execute("DELETE FROM progress WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
                     (session["user_id"], level_id, number))
    else:
        conn.execute("INSERT INTO progress (user_id, level_id, lesson_number, completed_at) VALUES (?,?,?,?)",
                     (session["user_id"], level_id, number, db.now_iso()))
    conn.commit()
    conn.close()
    return redirect(url_for("training_lesson", level_id=level_id, number=number))


@app.route("/reports", methods=["GET"])
@login_required
def reports():
    end = date.today()
    start = end - timedelta(days=30)
    return render_template("reports.html", start=start.isoformat(), end=end.isoformat())


@app.route("/reports/generate", methods=["POST"])
@login_required
def reports_generate():
    user = current_user()
    lang = get_lang(session)
    start = request.form.get("start_date") or (date.today() - timedelta(days=30)).isoformat()
    end = request.form.get("end_date") or date.today().isoformat()
    entries = [e for e in user_entries(user["id"]) if start <= e["date"] <= end]
    if not entries:
        return render_template("reports.html", start=start, end=end, error=t("report_no_data", lang))
    pdf = generate_report(entries, user, start, end, lang)
    fname = f"field-report-{start}-to-{end}.pdf"
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.route("/assistant", methods=["GET"])
@login_required
def assistant_page():
    return render_template("assistant.html")


@app.route("/assistant/ask", methods=["POST"])
@login_required
def assistant_ask():
    user = current_user()
    lang = get_lang(session)
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    entries = user_entries(user["id"])
    progress = user_progress(user["id"])
    reply = assistant_answer(message, entries, progress, user, lang)
    return jsonify({"reply": reply})


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    if request.method == "POST":
        name = request.form.get("name", "").strip() or user["name"]
        location = request.form.get("field_location", "").strip()
        conn = db.get_db()
        conn.execute("UPDATE users SET name = ?, field_location = ? WHERE id = ?",
                     (name, location, user["id"]))
        conn.commit()
        conn.close()
        return redirect(url_for("profile", saved=1))
    return render_template("profile.html", user=user, saved=request.args.get("saved"))


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/healthz")
def healthz():
    """Liveness probe for hosting platforms (Render/Fly health checks)."""
    try:
        conn = db.get_db()
        conn.execute("SELECT 1")
        conn.close()
        return jsonify({"ok": True, "db": db.db_kind()})
    except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
        log.warning("healthz db check failed: %s", exc)
        return jsonify({"ok": False, "error": "db unreachable"}), 503


db.init_db()
log.info("Field Agent ready (db=%s)", db.db_kind())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
