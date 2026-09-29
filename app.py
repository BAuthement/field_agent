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
                        get_lesson_body_html, anchor_end, split_lookback,
                        get_subjective_for,
                        get_level, get_quiz,
                        get_gates, gate_key_for, prev_level_with_lessons)
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


def user_lookbacks(user_id):
    """Look Back reflections (did_homework=1, or lesson-1 text answers),
    enriched with the lesson title, for donor reports."""
    conn = db.get_db()
    rows = conn.execute(
        "SELECT * FROM lookback_responses WHERE user_id = ? AND"
        " ((lesson_number >= 2 AND did_homework = 1) OR (lesson_number = 1 AND TRIM(answer_text) != ''))"
        " ORDER BY created_at", (user_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        les = get_lesson(d["level_id"], d["lesson_number"])
        lvl = get_level(d["level_id"])
        d["lesson_title"] = (f"{lvl['number']}: {lvl['name']} — {les['title']}"
                             if lvl and les else "")
        out.append(d)
    return out


def user_all_responses(user_id):
    """Every subjective text-box answer with its question metadata, grouped
    by section for the dashboard. Full text (privacy trimming applies only
    to the donor report)."""
    from curriculum import get_subjective_questions
    meta = {}
    for items in get_subjective_questions().values():
        for q in items:
            meta[q["id"]] = q
    conn = db.get_db()
    rows = conn.execute(
        "SELECT level_id, lesson_number, question_id, answer_text, updated_at"
        " FROM subjective_responses WHERE user_id = ? AND TRIM(answer_text) != ''"
        " ORDER BY updated_at", (user_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        q = meta.get(r["question_id"])
        if not q:
            continue
        lvl = get_level(r["level_id"])
        les = get_lesson(r["level_id"], r["lesson_number"])
        out.append({
            "qid": r["question_id"], "level_id": r["level_id"],
            "lesson_number": r["lesson_number"],
            "section_en": q["section_en"], "section_es": q["section_es"],
            "label_en": q["label_en"], "label_es": q["label_es"],
            "answer_text": r["answer_text"] or "",
            "lesson_title": (f"{lvl['number']}: {lvl['name']} — {les['title']}"
                             if lvl and les else ""),
        })
    return out


def user_strategy_responses(user_id):
    """Subjective text-box answers flagged for the donor report, joined with
    their question metadata."""
    from curriculum import get_subjective_questions
    meta = {}
    for _key, items in get_subjective_questions().items():
        for q in items:
            if q.get("donor_report"):
                meta[q["id"]] = q
    conn = db.get_db()
    rows = conn.execute(
        "SELECT level_id, lesson_number, question_id, answer_text, updated_at"
        " FROM subjective_responses WHERE user_id = ? AND TRIM(answer_text) != ''"
        " ORDER BY updated_at", (user_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        q = meta.get(r["question_id"])
        if not q:
            continue
        les = get_lesson(r["level_id"], r["lesson_number"])
        out.append({
            "section_en": q["section_en"], "section_es": q["section_es"],
            "label_en": q["label_en"], "label_es": q["label_es"],
            "answer_text": r["answer_text"] or "",
            "names_first_only": bool(q.get("names_first_only")),
            "lesson_title": les["title"] if les else "",
        })
    return out


def first_names_only(text):
    """Privacy: reduce a name list to first names only."""
    parts = [p.strip() for p in text.replace("\n", ",").split(",")]
    firsts = []
    for p in parts:
        toks = p.split()
        if toks:
            firsts.append(toks[0])
    return ", ".join(firsts)


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
        "lessons": sum(1 for (_lid, n) in progress if n >= 1),
        "followups": sum(1 for e in entries if e["follow_up"]),
    }
    return render_template("dashboard.html", user=user, stats=stats, recent=entries[:8],
                           responses=user_all_responses(user["id"]),
                           lookbacks=user_lookbacks(user["id"]))


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
        done = sum(1 for les in lvl["lessons"]
                   if les["number"] >= 1 and (lvl["id"], les["number"]) in progress)
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


def get_subj_responses(uid, level_id, number):
    conn = db.get_db()
    rows = conn.execute(
        "SELECT question_id, answer_text FROM subjective_responses"
        " WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
        (uid, level_id, number)).fetchall()
    conn.close()
    return {r["question_id"]: (r["answer_text"] or "") for r in rows}


def get_lookback(uid, level_id, number):
    conn = db.get_db()
    row = conn.execute(
        "SELECT * FROM lookback_responses WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
        (uid, level_id, number)).fetchone()
    conn.close()
    return dict(row) if row else None


def lookback_satisfied(resp, number):
    """Has the student completed this lesson's Look Back reflection?"""
    if not resp:
        return False
    answered = bool((resp["answer_text"] or "").strip())
    if number == 1:
        return answered  # the Introduction has no GOAL; reflection is text-only
    return resp["did_homework"] == 1 and answered


def _auto_log_experience(uid, user, text, lookback_id=None, subj_qid=None):
    """Auto-log a ministry activity when the text describes sharing the gospel.

    Returns (ask_count_entry_id or None, share_label). Dedupes on the link so
    resubmissions update instead of duplicating.
    """
    action = detect_ministry_action(text)
    if not action:
        return None, None
    atype, share_label = action
    count = extract_people_count(text)
    conn = db.get_db()
    if lookback_id is not None:
        row = conn.execute(
            "SELECT id, people_count FROM entries WHERE user_id = ? AND lookback_id = ?",
            (uid, lookback_id)).fetchone()
        link_col, link_val = "lookback_id", lookback_id
    else:
        row = conn.execute(
            "SELECT id, people_count FROM entries WHERE user_id = ? AND subj_question_id = ?",
            (uid, subj_qid)).fetchone()
        link_col, link_val = "subj_question_id", subj_qid
    notes = text[:200]
    loc = (user["field_location"] or "").strip()
    if row:
        conn.execute("UPDATE entries SET type = ?, notes = ? WHERE id = ?",
                     (atype, notes, row["id"]))
        entry_id = row["id"]
        if not row["people_count"] and count:
            conn.execute("UPDATE entries SET people_count = ? WHERE id = ?",
                         (count, entry_id))
    else:
        conn.execute(
            "INSERT INTO entries (user_id, type, date, location, people_count, notes,"
            " follow_up, created_at, source, reflection_id, lookback_id, subj_question_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, atype, date.today().isoformat(), loc, count or 0, notes,
             0, db.now_iso(), "reflection", None, lookback_id, subj_qid))
        entry_id = conn.execute(
            f"SELECT id FROM entries WHERE user_id = ? AND {link_col} = ?"
            " ORDER BY id DESC LIMIT 1", (uid, link_val)).fetchone()["id"]
    conn.commit()
    conn.close()
    already_counted = (row and row["people_count"]) or count
    return (None if already_counted else entry_id), share_label


def _valid_ask_count(uid, entry_id):
    if not entry_id:
        return None
    conn = db.get_db()
    row = conn.execute(
        "SELECT id FROM entries WHERE id = ? AND user_id = ? AND source = 'reflection'",
        (entry_id, uid)).fetchone()
    conn.close()
    return row["id"] if row else None


def _textbox_html(level_id, number, q, saved, lang, answered_qid=None,
                  err_qid=None, next_dest=None):
    import html as _html
    qid = q["id"]
    label = q["label_es"] if lang == "es" else q["label_en"]
    thanks = (f'<div class="alert">&#x2713; {_html.escape(t("answer_thanks", lang))}</div>'
              if answered_qid == qid else "")
    err = (f'<div class="alert warn">{_html.escape(t("answer_required", lang))}</div>'
           if err_qid == qid else "")
    nxt = (f'<input type="hidden" name="next" value="{_html.escape(next_dest)}">'
           if next_dest else "")
    return (
        f'<div class="textbox" id="tb-{_html.escape(qid)}">'
        f'<form method="post" action="{url_for("save_response", level_id=level_id, number=number)}">'
        f'<input type="hidden" name="question_id" value="{_html.escape(qid)}">{nxt}'
        f'<label for="ta-{_html.escape(qid)}"><strong>{_html.escape(label)}</strong></label>'
        f'<textarea id="ta-{_html.escape(qid)}" name="answer" rows="3" '
        f'placeholder="{_html.escape(t("answer_ph", lang))}">{_html.escape(saved or "")}</textarea>'
        f'<button class="btn small gold" type="submit">{t("answer_submit", lang)}</button>'
        f'</form>{thanks}{err}</div>'
    )


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
    # The Introduction (with its quiz, if any) must be finished before any
    # numbered lesson can be opened.
    if number >= 1 and (level_id, 0) not in user_progress(uid):
        return redirect(url_for("training_lesson", level_id=level_id, number=0))
    lang = get_lang(session)
    fb = session.pop("quiz_feedback", None)
    is_intro = (number == 0)
    lbl = request.args.get("share_label")
    share_label = lbl if lbl in SHARE_LABELS else None
    ask_count = _valid_ask_count(uid, request.args.get("ask_count", type=int))

    # Look Back gate (inline): lessons 1+ show only their Look Back section
    # until the reflection is answered. Introduction pages have no Look Back.
    lb_text, _lb_rest = split_lookback(level_id, number)
    lb_resp = get_lookback(uid, level_id, number) if lb_text else None
    if lb_text and not lookback_satisfied(lb_resp, number):
        import html as _html
        return render_template(
            "training_lesson.html", level=lvl, lesson=les, done=False,
            total=len(lvl["lessons"]), prev_n=None, next_n=None,
            questions=None, quiz_done=False, quiz_just_done=None,
            feedback=fb, body_html=_html.escape(lb_text),
            illustrations=[], lookback_gate=True, lb_resp=lb_resp,
            lb_error=request.args.get("lb_err"),
            lb_blocked=request.args.get("lb_blocked"), unanswered=[],
            ask_count=ask_count, share_label=share_label,
            is_intro=is_intro)

    # Full lesson view.
    progress = user_progress(uid)
    done = (level_id, number) in progress
    questions = get_quiz(level_id, number)
    qdone = (level_id, number) in quiz_done_for(uid)
    total = len(lvl["lessons"])
    prev_n = number - 1 if number >= 1 else None
    next_n = number + 1 if number < total else None

    subj = get_subjective_for(level_id, number)
    saved = get_subj_responses(uid, level_id, number) if subj else {}
    unanswered = [q for q in subj if not (saved.get(q["id"]) or "").strip()]
    inserts = []
    for q in subj:
        off = anchor_end(les["body"], q["anchor"])
        if off != -1:
            inserts.append((off, _textbox_html(
                level_id, number, q, saved.get(q["id"], ""), lang,
                answered_qid=request.args.get("answered"),
                err_qid=request.args.get("err"))))
    body_html = get_lesson_body_html(level_id, number, t("step_caption", lang),
                                     extra_inserts=inserts)
    return render_template("training_lesson.html", level=lvl, lesson=les, done=done,
                           total=total, prev_n=prev_n, next_n=next_n,
                           questions=questions, quiz_done=qdone,
                           quiz_just_done=request.args.get("quiz_done"),
                           feedback=fb, body_html=body_html,
                           illustrations=get_lesson_illustrations(level_id, number),
                           lookback_gate=False, unanswered=unanswered,
                           ask_count=ask_count, share_label=share_label,
                           is_intro=is_intro)


@app.route("/training/<level_id>/<int:number>/respond", methods=["POST"])
@login_required
def save_response(level_id, number):
    """Save one subjective text-box answer (upsert)."""
    uid = session["user_id"]
    lvl = get_level(level_id)
    les = get_lesson(level_id, number)
    if not lvl or not les:
        return redirect(url_for("training"))
    qid = request.form.get("question_id", "")
    if not any(q["id"] == qid for q in get_subjective_for(level_id, number)):
        return redirect(url_for("training_lesson", level_id=level_id, number=number))
    answer = request.form.get("answer", "").strip()
    if not answer:
        return redirect(url_for("training_lesson", level_id=level_id, number=number,
                                err=qid) + f"#tb-{qid}")
    now = db.now_iso()
    conn = db.get_db()
    cur = conn.execute(
        "UPDATE subjective_responses SET answer_text = ?, updated_at = ?"
        " WHERE user_id = ? AND level_id = ? AND lesson_number = ? AND question_id = ?",
        (answer, now, uid, level_id, number, qid))
    if cur.rowcount == 0:
        conn.execute(
            "INSERT INTO subjective_responses (user_id, level_id, lesson_number,"
            " question_id, answer_text, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (uid, level_id, number, qid, answer, now, now))
    conn.commit()
    conn.close()
    ask_count, share_label = _auto_log_experience(uid, current_user(), answer, subj_qid=qid)
    if request.form.get("next") == "dashboard":
        return redirect(url_for("dashboard") + f"#resp-{qid}")
    dest = url_for("training_lesson", level_id=level_id, number=number, answered=qid)
    if ask_count:
        dest = url_for("training_lesson", level_id=level_id, number=number,
                       answered=qid, ask_count=ask_count, share_label=share_label)
    return redirect(dest + f"#tb-{qid}")


@app.route("/training/<level_id>/<int:number>/lookback", methods=["POST"])
@login_required
def save_lookback(level_id, number):
    """Save the inline Look Back reflection (upsert)."""
    uid = session["user_id"]
    lvl = get_level(level_id)
    les = get_lesson(level_id, number)
    if not lvl or not les:
        return redirect(url_for("training"))
    lb_text, _ = split_lookback(level_id, number)
    if not lb_text:
        return redirect(url_for("training_lesson", level_id=level_id, number=number))
    answer = request.form.get("answer_text", "").strip()
    did = None
    if number >= 2:
        raw = request.form.get("did_homework")
        if raw not in ("yes", "no"):
            return redirect(url_for("training_lesson", level_id=level_id, number=number,
                                    lb_err="yn"))
        did = 1 if raw == "yes" else 0
        if did and not answer:
            return redirect(url_for("training_lesson", level_id=level_id, number=number,
                                    lb_err="text"))
    elif not answer:
        return redirect(url_for("training_lesson", level_id=level_id, number=number,
                                lb_err="text"))
    now = db.now_iso()
    conn = db.get_db()
    cur = conn.execute(
        "UPDATE lookback_responses SET did_homework = ?, answer_text = ?, updated_at = ?"
        " WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
        (did, answer, now, uid, level_id, number))
    if cur.rowcount == 0:
        conn.execute(
            "INSERT INTO lookback_responses (user_id, level_id, lesson_number,"
            " did_homework, answer_text, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (uid, level_id, number, did, answer, now, now))
    conn.commit()
    lb_id = conn.execute(
        "SELECT id FROM lookback_responses WHERE user_id = ? AND level_id = ? AND lesson_number = ?",
        (uid, level_id, number)).fetchone()["id"]
    conn.close()
    ask_count = share_label = None
    if lookback_satisfied({"did_homework": did, "answer_text": answer}, number):
        ask_count, share_label = _auto_log_experience(
            uid, current_user(), answer, lookback_id=lb_id)
    if request.form.get("next") == "dashboard":
        return redirect(url_for("dashboard") + f"#lb-{level_id}-{number}")
    if did == 0:
        # Encouragement/blocking path: keep them at the gate with the
        # "go do the homework" message, previous answers preserved.
        return redirect(url_for("training_lesson", level_id=level_id, number=number,
                                lb_blocked=1))
    if ask_count:
        return redirect(url_for("training_lesson", level_id=level_id, number=number,
                                ask_count=ask_count, share_label=share_label))
    return redirect(url_for("training_lesson", level_id=level_id, number=number))


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
    return redirect(url_for("training_lesson", level_id=level_id, number=number))


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
    # The Introduction (with its quiz, if any) must be finished before any
    # numbered lesson or its quiz can be opened.
    if number >= 1 and (level_id, 0) not in user_progress(uid):
        return redirect(url_for("training_lesson", level_id=level_id, number=0))
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
    # Completing: every subjective text box must be answered first.
    subj = get_subjective_for(level_id, number)
    if subj:
        saved = get_subj_responses(uid, level_id, number)
        if any(not (saved.get(q["id"]) or "").strip() for q in subj):
            conn.close()
            return redirect(url_for("training_lesson", level_id=level_id, number=number)
                            + "#lesson-complete")
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
    reflections = user_lookbacks(user["id"])
    strategy = user_strategy_responses(user["id"])
    if not entries and not reflections and not strategy:
        return render_template("reports.html", start=start, end=end, error=t("report_no_data", lang))
    pdf = generate_report(entries, user, start, end, lang, reflections, strategy,
                          first_names_only=first_names_only)
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
    return jsonify({"ok": True, "version": "2.4"})


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
