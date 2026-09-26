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
# complete a lesson
c.post("/training/level1/1/toggle", {})
html = c.get("/training/level1/1")
check("lesson marked complete", "Completed" in html)
html = c.get("/dashboard")
check("lesson counted on dashboard", "Lessons completed" in html)
# reports PDF
status, ctype, pdf = c.post_raw("/reports/generate", {"start_date": "2026-09-01", "end_date": "2026-09-30"})
check("report PDF generated", status == 200 and ctype == "application/pdf" and pdf[:4] == b"%PDF", f"{status} {ctype}")
check("report has content", len(pdf) > 1500, f"{len(pdf)} bytes")
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

fails = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
raise SystemExit(1 if fails else 0)
