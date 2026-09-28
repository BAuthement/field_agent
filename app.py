"""Field Agent \u2014 missionary field companion for MissionaryAgents / NPL Academy."""
import logging
import os
import random
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, jsonify, redirect, render_template, request, Response,
                   session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import db
from assistant import answer as assistant_answer
from curriculum import (get_curriculum, get_lesson, get_lesson_illustrations,
                        get_level, get_quiz,
                        get_gates, gate_key_for, prev_lesson_key, prev_level_with_lessons)
from experience import (SHARE_LABELS, detect_ministry_action,
                        extract_people_count)
from i18n import STRINGS, QUIZ_RIGHT, QUIZ_WRONG, get_lang, t
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


def quiz_done_for(user_id):
    conn = db.get_db()
    rows = conn.execute("SELECT level_id, lesson_number FROM quiz_done WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return {(r["level_id"], r["lesson_number"]) for r in rows}


def gate_attested(user_id, level_id):
    """True when the user may enter level_id (no gate, or gate self-attested)."""
    if not gate_key_for(level_id):
        return True
    conn = db.get_db()
    row = conn.execute("SELECT 1 FROM level_gates WHERE user_id = ? AND level_id = ?",
                       (user_id, level_id)).fetchone()
    conn.close()
    return bool(row)


def gate_redirect(level_id):
    """Redirect to the level-entry gate page when gated and unattested."""
    if not gate_attested(session["user_id"], level_id):
        return redirect(url_for("level_gate", level_id=level_id))
    return None


def get_reflection(user_id, level_id, number):
    conn = db.get_db()
    row = conn.execute(
        "SELECT * FROM homework_reflections WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
        (user_id, level_id, number)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_reflections(user_id):
    """Reflections with did_homework=1, enriched with the title of the lesson
    whose homework was reflected on (the lesson before the one being entered)."""
    conn = db.get_db()
    rows = conn.execute(
        "SELECT * FROM homework_reflections WHERE user_id = ? AND did_homework = 1 ORDER BY created_at",
        (user_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        prev = prev_lesson_key(d["level_id"], d["lesson_number"])
        les = get_lesson(prev[0], prev[1]) if prev else get_lesson(d["level_id"], d["lesson_number"])
        d["lesson_title"] = les["title"] if les else ""
        out.append(d)
    return out


def feedback_msg(pool, lang, key):
    """Random feedback message; never the same one twice in a row."""
    msgs = pool.get(lang, pool["en"])
    last = session.get("fb_" + key)
    choices = [m for m in msgs if m != last] or msgs
    msg = random.choice(choices)
    session["fb_" + key] = msg
    return msg


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
    blocked = gate_redirect(level_id)
    if blocked:
        return blocked
    progress = user_progress(session["user_id"])
    lessons = [{"lesson": les, "done": (level_id, les["number"]) in progress} for les in lvl["lessons"]]
    return render_template("training_level.html", level=lvl, lessons=lessons)


@app.route("/training/<level_id>/gate", methods=["GET", "POST"])
@login_required
def level_gate(level_id):
    """v2.1 — self-attested hard gate before entering Level 2/3.

    The previous level's lessons must all be complete before the checklist
    appears; every prerequisite must be checked plus the honesty affirmation.
    """
    uid = session["user_id"]
    lang = get_lang(session)
    lvl = get_level(level_id)
    key = gate_key_for(level_id) if lvl else None
    if not lvl or not key:
        return redirect(url_for("training"))
    level_label = f"{lvl['number']}: {lvl['name']}"
    if gate_attested(uid, level_id):
        return redirect(url_for("training_level", level_id=level_id))
    prev_lvl = prev_level_with_lessons(level_id)
    prev_label = f"{prev_lvl['number']}: {prev_lvl['name']}" if prev_lvl else ""
    progress = user_progress(uid)
    lessons_done = bool(prev_lvl) and all(
        (prev_lvl["id"], les["number"]) in progress for les in prev_lvl["lessons"])
    items = get_gates()[key]
    ctx = dict(level=lvl, level_label=level_label, prev_level=prev_lvl,
               prev_label=prev_label, items=items)
    if request.method == "POST":
        if not lessons_done or gate_attested(uid, level_id):
            return redirect(url_for("level_gate", level_id=level_id))
        all_checked = all(request.form.get(f"item_{i}") == "yes" for i in range(len(items)))
        affirmed = request.form.get("affirm") == "yes"
        if all_checked and affirmed:
            conn = db.get_db()
            conn.execute("INSERT INTO level_gates (user_id, level_id, attested_at) VALUES (?,?,?)",
                         (uid, level_id, db.now_iso()))
            conn.commit()
            conn.close()
            return redirect(url_for("training_level", level_id=level_id))
        return render_template("level_gate.html", mode="checklist", error=t("lgate_error", lang), **ctx)
    return render_template("level_gate.html",
                           mode="checklist" if lessons_done else "lessons_first",
                           error=None, **ctx)


@app.route("/training/<level_id>/<int:number>")
@login_required
def training_lesson(level_id, number):
    lvl = get_level(level_id)
    les = get_lesson(level_id, number)
    if not lvl or not les:
        return redirect(url_for("training"))
    blocked = gate_redirect(level_id)
    if blocked:
        return blocked
    uid = session["user_id"]
    progress = user_progress(uid)
    # Homework reflection gate: entering a lesson whose previous lesson is
    # completed requires reflecting on the previous lesson's homework first.
    prev = prev_lesson_key(level_id, number)
    if prev and prev in progress:
        refl = get_reflection(uid, level_id, number)
        mode = request.args.get("mode", "form")
        prev_les = get_lesson(prev[0], prev[1])
        gate_ctx = dict(level=lvl, lesson=les, prev_lesson=prev_les,
                        prev_level_id=prev[0], error=None)
        if mode == "affirmed" and refl and refl["did_homework"]:
            ask_count = request.args.get("ask_count", type=int)
            share_entry = share_label = None
            if ask_count:
                conn = db.get_db()
                share_entry = conn.execute(
                    "SELECT id FROM entries WHERE id = ? AND user_id = ? AND source = 'reflection'",
                    (ask_count, uid)).fetchone()
                conn.close()
                if share_entry:
                    lbl = request.args.get("share_label")
                    share_label = lbl if lbl in SHARE_LABELS else "share_gospel"
            return render_template("homework_gate.html", mode="affirmed",
                                   ask_count=share_entry["id"] if share_entry else None,
                                   share_label=share_label, **gate_ctx)
        if not refl or not refl["did_homework"]:
            show = "blocked" if mode == "blocked" else "form"
            return render_template("homework_gate.html", mode=show, **gate_ctx)
    done = (level_id, number) in progress
    questions = get_quiz(level_id, number)
    qdone = (level_id, number) in quiz_done_for(uid)
    total = len(lvl["lessons"])
    prev_n = number - 1 if number > 1 else None
    next_n = number + 1 if number < total else None
    fb = session.pop("quiz_feedback", None)
    return render_template("training_lesson.html", level=lvl, lesson=les, done=done,
                           total=total, prev_n=prev_n, next_n=next_n,
                           questions=questions, quiz_done=qdone,
                           quiz_just_done=request.args.get("quiz_done"),
                           feedback=fb,
                           illustrations=get_lesson_illustrations(level_id, number))


@app.route("/training/<level_id>/<int:number>/reflect", methods=["POST"])
@login_required
def reflect_homework(level_id, number):
    uid = session["user_id"]
    user = current_user()
    lang = get_lang(session)
    lvl = get_level(level_id)
    les = get_lesson(level_id, number)
    if not lvl or not les:
        return redirect(url_for("training"))
    did = request.form.get("did_homework") == "yes"
    positive = request.form.get("positive_experience", "").strip()
    improve = request.form.get("improve", "").strip()
    if did and (not positive or not improve):
        prev = prev_lesson_key(level_id, number)
        prev_les = get_lesson(prev[0], prev[1]) if prev else None
        return render_template("homework_gate.html", level=lvl, lesson=les,
                               prev_lesson=prev_les, prev_level_id=prev[0] if prev else level_id,
                               mode="form", error=t("gate_required", lang))
    existing = get_reflection(uid, level_id, number)
    conn = db.get_db()
    if existing:
        conn.execute("UPDATE homework_reflections SET did_homework = ?, positive_experience = ?,"
                     " improve = ?, created_at = ? WHERE id = ?",
                     (1 if did else 0, positive, improve, db.now_iso(), existing["id"]))
        refl_id = existing["id"]
    else:
        conn.execute("INSERT INTO homework_reflections (user_id, level_id, lesson_number, did_homework,"
                     " positive_experience, improve, created_at) VALUES (?,?,?,?,?,?,?)",
                     (uid, level_id, number, 1 if did else 0, positive, improve, db.now_iso()))
        refl_id = conn.execute(
            "SELECT id FROM homework_reflections WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
            (uid, level_id, number)).fetchone()["id"]

    # Experience tracking: when the described experience mentions sharing the
    # gospel (testimony, 3-Circles, ...), log it as an activity automatically
    # so dashboard stats and donor reports pick it up without re-entry.
    ask_count_entry = None
    share_label = None
    if did:
        action = detect_ministry_action(positive + "\n" + improve)
        if action:
            atype, share_label = action
            count = extract_people_count(positive + "\n" + improve)
            notes = positive[:200]
            loc = (user["field_location"] or "").strip()
            linked = conn.execute(
                "SELECT id, people_count FROM entries WHERE user_id = ? AND reflection_id = ?",
                (uid, refl_id)).fetchone()
            if linked:
                conn.execute("UPDATE entries SET type = ?, notes = ? WHERE id = ?",
                             (atype, notes, linked["id"]))
                entry_id = linked["id"]
                if not linked["people_count"] and count:
                    conn.execute("UPDATE entries SET people_count = ? WHERE id = ?",
                                 (count, entry_id))
                elif not linked["people_count"]:
                    ask_count_entry = entry_id
            else:
                conn.execute(
                    "INSERT INTO entries (user_id, type, date, location, people_count, notes,"
                    " follow_up, created_at, source, reflection_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (uid, atype, date.today().isoformat(), loc, count or 0, notes,
                     0, db.now_iso(), "reflection", refl_id))
                entry_id = conn.execute(
                    "SELECT id FROM entries WHERE user_id = ? AND reflection_id = ?"
                    " ORDER BY id DESC LIMIT 1", (uid, refl_id)).fetchone()["id"]
                if not count:
                    ask_count_entry = entry_id
    conn.commit()
    conn.close()
    if did:
        if ask_count_entry:
            return redirect(url_for("training_lesson", level_id=level_id, number=number,
                                    mode="affirmed", ask_count=ask_count_entry,
                                    share_label=share_label))
        return redirect(url_for("training_lesson", level_id=level_id, number=number, mode="affirmed"))
    return redirect(url_for("training_lesson", level_id=level_id, number=number, mode="blocked"))


@app.route("/training/<level_id>/<int:number>/count", methods=["POST"])
@login_required
def save_shared_count(level_id, number):
    """Fill in the people count for an auto-logged reflection entry."""
    uid = session["user_id"]
    entry_id = request.form.get("entry_id", type=int)
    try:
        count = int(request.form.get("people_count") or 0)
    except (TypeError, ValueError):
        count = 0
    if entry_id and count > 0:
        conn = db.get_db()
        own = conn.execute("SELECT id FROM entries WHERE id = ? AND user_id = ?",
                           (entry_id, uid)).fetchone()
        if own:
            conn.execute("UPDATE entries SET people_count = ? WHERE id = ?", (count, entry_id))
            conn.commit()
        conn.close()
    return redirect(url_for("training_lesson", level_id=level_id, number=number, mode="affirmed"))


@app.route("/training/<level_id>/<int:number>/quiz", methods=["GET", "POST"])
@login_required
def lesson_quiz(level_id, number):
    uid = session["user_id"]
    lang = get_lang(session)
    lvl = get_level(level_id)
    les = get_lesson(level_id, number)
    questions = get_quiz(level_id, number)
    if not lvl or not les or not questions:
        return redirect(url_for("training_lesson", level_id=level_id, number=number))
    blocked = gate_redirect(level_id)
    if blocked:
        return blocked
    if (level_id, number) in quiz_done_for(uid):
        return redirect(url_for("training_lesson", level_id=level_id, number=number))
    total = len(questions)
    st = session.get("quiz") or {}
    if st.get("lid") != level_id or st.get("n") != number or st.get("idx", 0) >= total:
        st = {"lid": level_id, "n": number, "idx": 0,
              "order": random.sample(range(3), 3)}
    if request.method == "POST":
        q = questions[st["idx"]]
        order = st["order"]
        correct_pos = order.index(q["answer"])
        try:
            picked = int(request.form.get("choice", -1))
        except (TypeError, ValueError):
            picked = -1
        if picked == correct_pos:
            msg = feedback_msg(QUIZ_RIGHT, lang, "right")
            st["idx"] += 1
            if st["idx"] >= total:
                conn = db.get_db()
                if (level_id, number) not in quiz_done_for(uid):
                    conn.execute("INSERT INTO quiz_done (user_id, level_id, lesson_number, completed_at)"
                                 " VALUES (?,?,?,?)", (uid, level_id, number, db.now_iso()))
                    conn.commit()
                conn.close()
                session.pop("quiz", None)
                session["quiz_feedback"] = {"ok": True, "msg": msg}
                return redirect(url_for("training_lesson", level_id=level_id, number=number,
                                        quiz_done=1))
            st["order"] = random.sample(range(3), 3)
            session["quiz"] = st
            session["quiz_feedback"] = {"ok": True, "msg": msg}
        else:
            session["quiz_feedback"] = {"ok": False,
                                        "msg": feedback_msg(QUIZ_WRONG, lang, "wrong")}
            session["quiz"] = st
        return redirect(url_for("lesson_quiz", level_id=level_id, number=number))
    # GET: render current question
    q = questions[st["idx"]]
    order = st["order"]
    opts = q["options_es"] if lang == "es" else q["options_en"]
    fb = session.pop("quiz_feedback", None)
    session["quiz"] = st
    return render_template("quiz.html", level=lvl, lesson=les, n=st["idx"] + 1,
                           total=total, question=q["q_es"] if lang == "es" else q["q_en"],
                           options=[opts[i] for i in order], feedback=fb,
                           required=request.args.get("required"))


@app.route("/training/<level_id>/<int:number>/completed")
@login_required
def lesson_completed(level_id, number):
    lvl = get_level(level_id)
    les = get_lesson(level_id, number)
    if not lvl or not les:
        return redirect(url_for("training"))
    total = len(lvl["lessons"])
    next_n = number + 1 if number < total else None
    return render_template("lesson_completed.html", level=lvl, lesson=les, next_n=next_n)


@app.route("/training/<level_id>/<int:number>/toggle", methods=["POST"])
@login_required
def toggle_lesson(level_id, number):
    uid = session["user_id"]
    blocked = gate_redirect(level_id)
    if blocked:
        return blocked
    conn = db.get_db()
    exists = conn.execute(
        "SELECT 1 FROM progress WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
        (uid, level_id, number)).fetchone()
    if exists:
        conn.execute("DELETE FROM progress WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
                     (uid, level_id, number))
        conn.commit()
        conn.close()
        return redirect(url_for("training_lesson", level_id=level_id, number=number))
    # Completing: the lesson quiz must be done first when one exists.
    if get_quiz(level_id, number) and (level_id, number) not in quiz_done_for(uid):
        conn.close()
        return redirect(url_for("lesson_quiz", level_id=level_id, number=number, required=1))
    conn.execute("INSERT INTO progress (user_id, level_id, lesson_number, completed_at) VALUES (?,?,?,?)",
                 (uid, level_id, number, db.now_iso()))
    conn.commit()
    conn.close()
    return redirect(url_for("lesson_completed", level_id=level_id, number=number))


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
    reflections = user_reflections(user["id"])
    if not entries and not reflections:
        return render_template("reports.html", start=start, end=end, error=t("report_no_data", lang))
    pdf = generate_report(entries, user, start, end, lang, reflections)
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
    return jsonify({"ok": True, "version": "2.2"})


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
