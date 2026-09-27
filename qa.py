"""Self-QA: exercise every Field Agent flow against the local server."""
import http.cookiejar, json, urllib.parse, urllib.request

BASE = "http://127.0.0.1:5055"
results = []

def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f" ({detail})" if detail and not cond else ""))

class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def get(self, path):
        return self.opener.open(BASE + path).read().decode()
    def post(self, path, data):
        enc = urllib.parse.urlencode(data).encode()
        return self.opener.open(BASE + path, enc).read().decode()
    def post_json(self, path, obj):
        req = urllib.request.Request(BASE + path, json.dumps(obj).encode(),
                                     {"Content-Type": "application/json"})
        return json.loads(self.opener.open(req).read().decode())
    def post_raw(self, path, data):
        enc = urllib.parse.urlencode(data).encode()
        r = self.opener.open(BASE + path, enc)
        return r.status, r.headers.get("Content-Type"), r.read()

c = Client()
# health
check("health", "ok" in c.get("/health"))
# register
html = c.post("/register", {"name": "Test Missionary", "email": "test@field.org",
                            "password": "secret123", "field_location": "Managua, Nicaragua"})
check("register -> dashboard", "Welcome back" in html or "Bienvenido" in html, html[:80])
# log entries
c.post("/log", {"type": "gospel_conversation", "date": "2026-09-20", "location": "Managua",
                "people_count": "5", "notes": "Shared the 3-Circles with a family.", "follow_up": "1"})
c.post("/log", {"type": "baptism", "date": "2026-09-22", "location": "Masaya",
                "people_count": "2", "notes": "Baptized two new believers!"})
html = c.get("/log")
check("2 entries logged", html.count('class="entry"') == 2, f"found {html.count(chr(39)+'entry'+chr(39))}")
check("follow-up badge", "Needs follow-up" in html)
# dashboard stats
html = c.get("/dashboard")
check("dashboard stats", all(x in html for x in ["Activities logged", "People reached", "Baptisms"]))
# training pages
html = c.get("/training")
check("training levels", all(x in html for x in ["Seed Sower", "Church Planter", "Church Multiplier", "Movement Trainer"]))
html = c.get("/training/level1")
check("level1 lessons list", "Father" in html and "S.W.A.P." in html)
html = c.get("/training/level1/1")
check("lesson 1 real content", "Father\u2019s Heart" in html and "Look Back" in html and "G.O.A.L." in html)
# ---- v2: quiz-gated lesson completion ----
import html as _html, re as _re, subprocess as _sp, tempfile as _tf
from curriculum import get_quiz as _get_quiz, get_quizzes as _get_quizzes, get_level as _get_level
from i18n import QUIZ_RIGHT as _QR, QUIZ_WRONG as _QW

def _unesc(s):
    return _html.unescape(s)

def _quiz_options(page_html):
    return [o[1].strip() for o in _re.findall(r'value="(\d)"[^>]*>\s*([^<]+)</label>', _unesc(page_html))]

def _answer_correct(client, base, qs, lang="en"):
    """Answer every quiz question correctly. Returns final page html."""
    idx = 0
    page_html = client.get(base + "/quiz")
    while "quiz-opt" in page_html and idx < len(qs) + 2:
        q = qs[idx]
        want = (q["options_es"] if lang == "es" else q["options_en"])[q["answer"]]
        opts = _quiz_options(page_html)
        pos = opts.index(want)
        page_html = client.post(base + "/quiz", {"choice": str(pos)})
        idx += 1
    return page_html

_quiz_keys = sorted(_get_quizzes().keys(), key=lambda k: (k.split(":")[0], int(k.split(":")[1])))
check("v2 quizzes.json loaded", len(_quiz_keys) > 0, f"{len(_quiz_keys)} lessons with quizzes")
if _quiz_keys:
    _main_key = next((k for k in _quiz_keys if len(_get_quizzes()[k]) >= 2), _quiz_keys[0])
    _lid, _num = _main_key.split(":"); _num = int(_num)
    _base = f"/training/{_lid}/{_num}"
    _qs = _get_quiz(_lid, _num)
else:
    _main_key = _lid = _num = _base = _qs = None

if _quiz_keys:
    # toggle without quiz -> sent to quiz (urllib follows the redirect)
    page_html = c.post(_base + "/toggle", {})
    check("v2 quiz gate blocks completion", "Check your understanding" in page_html and "Question 1 of" in page_html)

    # wrong -> encouragement + retry on same question
    page_html = c.get(_base + "/quiz")
    _opts = _quiz_options(page_html)
    _want = _qs[0]["options_en"][_qs[0]["answer"]]
    _wrong = (_opts.index(_want) + 1) % 3
    page_html = c.post(_base + "/quiz", {"choice": str(_wrong)})
    check("v2 wrong answer encourages retry", "Question 1 of" in page_html
          and any(m in _unesc(page_html) for m in _QW["en"]), page_html[:120])
    # correct -> advance with congratulations
    page_html = c.post(_base + "/quiz", {"choice": str(_opts.index(_want))})
    check("v2 correct answer advances", "Question 2 of" in page_html
          and any(m in _unesc(page_html) for m in _QR["en"]), page_html[:120])

    # finish the quiz, then completion works and shows homework reminder
    page_html = _answer_correct(c, _base, _qs[1:], lang="en") if len(_qs) > 1 else c.get(_base)
    check("v2 quiz completion banner", "Quiz complete!" in page_html)
    page_html = c.post(_base + "/toggle", {})
    check("v2 lesson marked complete", "Lesson complete" in page_html)
    check("v2 homework reminder shown", "Look Forward homework" in page_html and "obedient" in page_html)
    page_html = c.get(_base)
    check("v2 lesson shows completed", "Completed" in page_html)
    page_html = c.get("/dashboard")
    check("lesson counted on dashboard", "Lessons completed" in page_html)
# ---- v2: homework reflection gate ----
_v2_reflection_done = False
if _quiz_keys:
    from curriculum import prev_lesson_key as _prev_key
    _next = next((k for k in _quiz_keys
                  if _prev_key(k.split(":")[0], int(k.split(":")[1])) == (_lid, _num)), None)
    check("v2 next lesson exists for gate test", _next is not None)
    if _next:
        _nlid, _nnum = _next.split(":"); _nnum = int(_nnum)
        _nbase = f"/training/{_nlid}/{_nnum}"
        page_html = c.get(_nbase)
        check("v2 reflection gate form", "Before you begin this lesson" in page_html
              and 'name="did_homework"' in page_html)
        page_html = c.post(_nbase + "/reflect", {"did_homework": "no"})
        check("v2 gate blocks without homework", "do the homework first" in page_html)
        page_html = c.get(_nbase)
        check("v2 gate still blocks lesson", "lesson-body" not in page_html
              and 'name="did_homework"' in page_html)
        page_html = c.post(_nbase + "/reflect", {"did_homework": "yes",
                                                 "positive_experience": "", "improve": ""})
        check("v2 gate requires all answers", "answer all three" in page_html)
        page_html = c.post(_nbase + "/reflect", {"did_homework": "yes",
            "positive_experience": "Shared the 3-Circles with a family in Managua.",
            "improve": "I could follow up with them this week."})
        check("v2 gate affirmation", "You are growing!" in page_html)
        page_html = c.get(_nbase)
        check("v2 lesson unlocked after reflection",
              "lesson-body" in page_html or "Check your understanding" in page_html)
        _v2_reflection_done = True
# reports PDF
status, ctype, pdf = c.post_raw("/reports/generate", {"start_date": "2026-09-01", "end_date": "2026-09-30"})
check("report PDF generated", status == 200 and ctype == "application/pdf" and pdf[:4] == b"%PDF", f"{status} {ctype}")
check("report has content", len(pdf) > 1500, f"{len(pdf)} bytes")
# v2: homework reflections appear in the donor PDF
import shutil as _shutil
if _shutil.which("pdftotext"):
    with _tf.NamedTemporaryFile(suffix=".pdf", delete=False) as _f:
        _f.write(pdf); _pdf_path = _f.name
    _txt = _sp.run(["pdftotext", _pdf_path, "-"], capture_output=True, text=True).stdout
    if _v2_reflection_done:
        check("v2 report has ministry experiences", "Ministry experiences" in _txt)
        check("v2 report includes reflection text",
              "Shared the 3-Circles with a family in Managua." in _txt
              and "follow up with them this week" in _txt)
    else:
        check("v2 report reflections skipped (no quiz data)", True)
else:
    check("v2 report reflections", False, "pdftotext not installed")
# assistant
r = c.post_json("/assistant/ask", {"message": "weekly"})
check("assistant weekly summary", "2 activities" in r["reply"] or "activities" in r["reply"], r["reply"][:100])
r = c.post_json("/assistant/ask", {"message": "donor"})
check("assistant donor draft", "Managua" in r["reply"] and "baptism" in r["reply"].lower(), r["reply"][:100])
r = c.post_json("/assistant/ask", {"message": "quiz"})
check("assistant quiz", "Lesson" in r["reply"] and "G.O.A.L." in r["reply"], r["reply"][:100])
r = c.post_json("/assistant/ask", {"message": "hola"})
check("assistant greeting", len(r["reply"]) > 10)
# spanish toggle
c.get("/lang/es")
html = c.get("/dashboard")
check("spanish UI", "Actividades registradas" in html and "Bienvenido" in html)
r = c.post_json("/assistant/ask", {"message": "weekly"})
check("assistant spanish", "actividades" in r["reply"].lower(), r["reply"][:100])
c.get("/lang/en")
# ---- v2: Spanish quiz (fresh user, full wrong->correct flow in ES) ----
if _quiz_keys:
    c5 = Client()
    c5.post("/register", {"name": "Maria Prueba", "email": "maria@field.org", "password": "secret123"})
    c5.get("/lang/es")
    page_html = c5.get(_base + "/quiz")
    _q0 = _qs[0]
    check("v2 ES quiz question", _q0["q_es"] in _unesc(page_html), page_html[:120])
    _opts = _quiz_options(page_html)
    _want = _q0["options_es"][_q0["answer"]]
    check("v2 ES quiz options", _want in _opts and len(_opts) == 3)
    _wrong = (_opts.index(_want) + 1) % 3
    page_html = c5.post(_base + "/quiz", {"choice": str(_wrong)})
    check("v2 ES wrong-answer encouragement",
          "Pregunta 1 de" in page_html and any(m in _unesc(page_html) for m in _QW["es"]))
    page_html = c5.post(_base + "/quiz", {"choice": str(_opts.index(_want))})
    check("v2 ES congrats message",
          any(m in _unesc(page_html) for m in _QR["es"]), _unesc(page_html)[:200])
    page_html = _answer_correct(c5, _base, _qs[1:], lang="es")
    check("v2 ES quiz completion", "Cuestionario completo" in page_html)
    page_html = c5.post(_base + "/toggle", {})
    check("v2 ES homework reminder", "Mira Adelante" in page_html or "tarea" in page_html)
# data isolation: second user sees nothing of first
c2 = Client()
c2.post("/register", {"name": "Other Worker", "email": "other@field.org", "password": "secret123"})
html = c2.get("/log")
check("user isolation (entries)", 'class="entry"' not in html)
html = c2.get("/dashboard")
check("user isolation (stats zero)", ">0<" in html)  # zeros render as >0<
# wrong login rejected
c3 = Client()
html = c3.post("/login", {"email": "test@field.org", "password": "wrong"})
check("bad login rejected", "Invalid email or password" in html)
# unauthenticated redirect
c4 = Client()
try:
    html = c4.get("/dashboard")
    check("auth guard", "Log in" in html)
except Exception as e:
    check("auth guard", False, str(e))

# ---- v2.1: level-entry hard gate (self-attested prerequisites) ----
check("v2.1 health version", '"2.1"' in c.get("/health") or "2.1" in c.get("/health"))

def _complete_lesson(client, lid, num, lang="en"):
    """Full lesson flow: reflection gate (if any) -> quiz -> mark complete."""
    base = f"/training/{lid}/{num}"
    qs = _get_quiz(lid, num)
    page = client.get(base)
    if 'name="did_homework"' in page:
        client.post(base + "/reflect", {"did_homework": "yes",
            "positive_experience": "Shared the gospel in the harvest.",
            "improve": "I could pray more before going out."})
        page = client.get(base)
    if qs:
        page = _answer_correct(client, base, qs, lang=lang)
    return client.post(base + "/toggle", {})

c6 = Client()
c6.post("/register", {"name": "Gate Tester", "email": "gate1@field.org", "password": "secret123"})
html = c6.get("/training/level2")
check("v2.1 level2 blocked before lessons", "Finish your lessons first" in html
      and 'name="item_0"' not in html, _unesc(html)[:150])
html = c6.get("/training/level2/1")
check("v2.1 lesson deep-link blocked", "Finish your lessons first" in html
      and "lesson-body" not in html)
html = c6.post("/training/level2/gate",
               {f"item_{i}": "yes" for i in range(5)} | {"affirm": "yes"})
html = c6.get("/training/level2")
check("v2.1 premature attestation rejected", "Finish your lessons first" in html)

_l1_lessons = [les["number"] for les in _get_level("level1")["lessons"]]
for _n in _l1_lessons:
    _complete_lesson(c6, "level1", _n)
html = c6.get("/training/level2")
check("v2.1 checklist appears after lessons", "Prerequisites for" in html
      and 'name="item_4"' in html and "before God" in html, _unesc(html)[:150])
html = c6.post("/training/level2/gate",
               {f"item_{i}": "yes" for i in range(4)} | {"affirm": "yes"})
check("v2.1 partial attestation rejected", "check every item" in html, _unesc(html)[:150])
html = c6.get("/training/level2")
check("v2.1 still blocked after partial", "Prerequisites for" in html)
html = c6.post("/training/level2/gate",
               {f"item_{i}": "yes" for i in range(5)} | {"affirm": "yes"})
check("v2.1 full attestation unlocks level2", "Church Planter" in html
      and "Prerequisites for" not in html, _unesc(html)[:150])
html = c6.get("/training/level2/1")
check("v2.1 level2 lesson reachable (reflection gate first)",
      'name="did_homework"' in html and "lesson-body" not in html)
html = c6.post("/training/level2/1/reflect", {"did_homework": "yes",
    "positive_experience": "Led a friend to Christ at the House of Peace.",
    "improve": "I could share my testimony more boldly."})
html = c6.get("/training/level2/1")
check("v2.1 level2 lesson body renders", "lesson-body" in html)
html = c6.get("/training/level3")
check("v2.1 level3 gate lessons-first", "Finish your lessons first" in html)
html = c6.get("/training/level2/gate")
check("v2.1 gate revisits redirect into level", "Church Planter" in html
      and "Prerequisites for" not in html)

# isolation: another user's attestation does not unlock this user
c7 = Client()
c7.post("/register", {"name": "Gate Tester Dos", "email": "gate2@field.org", "password": "secret123"})
html = c7.get("/training/level2")
check("v2.1 gate isolation per user", "Finish your lessons first" in html)

# ES gate page (fresh user, Spanish)
c8 = Client()
c8.post("/register", {"name": "Probador Puerta", "email": "gate3@field.org", "password": "secret123"})
c8.get("/lang/es")
for _n in _l1_lessons:
    _complete_lesson(c8, "level1", _n, lang="es")
html = c8.get("/training/level2")
check("v2.1 ES checklist renders", "Requisitos para" in html
      and "Confirmo delante de Dios" in html, _unesc(html)[:150])
html = c8.get("/training/level3")
check("v2.1 ES lessons-first renders", "Termina tus lecciones primero" in html)

# migration: v1-schema DB gains level_gates, old data intact
import sqlite3 as _sqlite3
_tmpdb = _tf.NamedTemporaryFile(suffix=".db", delete=False); _tmpdb.close()
_con = _sqlite3.connect(_tmpdb.name)
_con.executescript(
    "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
    " email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, field_location TEXT DEFAULT '',"
    " language TEXT DEFAULT 'en', created_at TEXT NOT NULL);"
    "CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,"
    " type TEXT NOT NULL, date TEXT NOT NULL, location TEXT DEFAULT '',"
    " people_count INTEGER DEFAULT 0, notes TEXT DEFAULT '', follow_up INTEGER DEFAULT 0,"
    " created_at TEXT NOT NULL);"
    "CREATE TABLE progress (user_id INTEGER NOT NULL, level_id TEXT NOT NULL,"
    " lesson_number INTEGER NOT NULL, completed_at TEXT NOT NULL,"
    " PRIMARY KEY (user_id, level_id, lesson_number));")
_con.execute("INSERT INTO users (name, email, password_hash, created_at)"
             " VALUES ('Old User', 'old@field.org', 'x', '2026-01-01')")
_con.execute("INSERT INTO progress (user_id, level_id, lesson_number, completed_at)"
             " VALUES (1, 'level1', 1, '2026-01-02')")
_con.commit(); _con.close()
import db as _db
_db.SQLITE_PATH = _tmpdb.name
_db.init_db()
_con = _sqlite3.connect(_tmpdb.name)
_tables = {r[0] for r in _con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
_old_users = _con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
_old_prog = _con.execute("SELECT COUNT(*) FROM progress").fetchone()[0]
_con.close()
check("v2.1 migration adds level_gates, keeps data",
      "level_gates" in _tables and _old_users == 1 and _old_prog == 1, str(sorted(_tables)))

fails = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
raise SystemExit(1 if fails else 0)
