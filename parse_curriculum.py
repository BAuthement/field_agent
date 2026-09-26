"""Parse the three NPL Academy manuals into structured curriculum JSON."""
import json, re

LEVELS = [
    ("level1", "Level 1", "Seed Sower",
     "How to spread the gospel and gather a group of seekers and new believers. This is where every disciple begins.",
     "https://missionaryagents.org/npl-level-1-seed-sower.pdf"),
    ("level2", "Level 2", "Church Planter",
     "How to form your group of new believers into a healthy church that grows deep and wide.",
     "https://missionaryagents.org/npl-level-2-church-planter.pdf"),
    ("level3", "Level 3", "Church Multiplier",
     "How to train your church to start the next generation of churches \u2014 and the generation after that.",
     "https://missionaryagents.org/npl-level-3-church-multiplier.pdf"),
]

FOOTER_RE = re.compile(r"Page \d+ of \d+\s*Noplaceleft\.academy Level \d+ Training Manual \(version 5\.0\)\s*", re.I)
UNDER_RE = re.compile(r"_{10,}\s*")
HEADER_RE = re.compile(r"^LESSON (\d+):\s*(.+?)\s*$", re.I | re.M)

def clean(text):
    text = FOOTER_RE.sub(" ", text)
    text = UNDER_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()

def smart_title(t):
    t = re.sub(r"\s+\d+\s*$", "", t).strip()  # strip TOC page numbers
    if t.isupper():
        return " ".join(w[:1].upper() + w[1:].lower() for w in t.split())
    return t

TITLE_FIXES = {
    "S.w.a.p.": "S.W.A.P.",
    "Mawl": "MAWL",
    "3-circles": "3-Circles",
    "5-part Strategy / 4-fields Tools": "5-Part Strategy / 4-Fields Tools",
    "Entry Strategy \u2013 House Of Peace Map": "Entry Strategy \u2013 House of Peace Map",
    "(t1) Timing": "(T1) Timing", "(t2) Targets": "(T2) Targets",
    "(t5) Training": "(T5) Training", "(t6) Tracking": "(T6) Tracking",
    "(t7) Troubleshooting": "(T7) Troubleshooting", "(t8) Treasure": "(T8) Treasure",
    "5 Levels Of Leadership": "5 Levels of Leadership",
    "Lifecycle Of Movement": "Lifecycle of Movement",
}

def parse_level(fname):
    raw = open(f"/tmp/field-agent/{fname}.txt").read()
    matches = list(HEADER_RE.finditer(raw))
    mains = [(m, int(m.group(1)), smart_title(m.group(2))) for m in matches
             if m.group(2).strip().lower() != "look forward"]
    # pair each header with its chunk; keep only real lessons:
    # real lesson bodies always open with "Look Back:"; TOC ghosts don't.
    paired = []
    seen = set()
    for idx, (m, num, title) in enumerate(mains):
        start = m.end()
        end = mains[idx + 1][0].start() if idx + 1 < len(mains) else len(raw)
        chunk = raw[start:end]
        if len(chunk.strip()) > 500 and "look back" in chunk[:1500].lower() and num not in seen:
            seen.add(num)
            paired.append((num, title, chunk))
    paired.sort(key=lambda p: p[0])
    lessons = []
    for num, title, chunk in paired:
        # split body / look-forward
        lf = re.search(rf"^LESSON {num}:\s*Look Forward\s*$", chunk, re.I | re.M)
        if lf:
            body, look = chunk[:lf.start()], chunk[lf.end():]
        else:
            body, look = chunk, ""
        lessons.append({
            "number": num,
            "title": TITLE_FIXES.get(title, title),
            "body": clean(body),
            "look_forward": clean(look),
        })
    return lessons

curriculum = {"levels": []}
for lid, lnum, lname, desc, pdf in LEVELS:
    lessons = parse_level(lid)
    curriculum["levels"].append({
        "id": lid, "number": lnum, "name": lname,
        "description": desc, "manual_url": pdf,
        "lesson_count": len(lessons), "lessons": lessons,
    })
    print(lid, "->", len(lessons), "lessons")

# Levels 4-5: appointment only (from the Academy page)
curriculum["levels"].append({
    "id": "level4", "number": "Level 4", "name": "Movement Trainer",
    "description": "How to grow your network of churches beyond the fourth generation.",
    "manual_url": "", "lesson_count": 0, "lessons": [],
    "locked_note": "Training available by appointment only. Contact NoPlaceLeft Academy to enroll.",
})
curriculum["levels"].append({
    "id": "level5", "number": "Level 5", "name": "Strategy Coordinator",
    "description": "How to mobilize a network of churches to achieve NoPlaceLeft across a large geographical area.",
    "manual_url": "", "lesson_count": 0, "lessons": [],
    "locked_note": "Training available by appointment only. Contact NoPlaceLeft Academy to enroll.",
})

curriculum["attribution"] = ("Curriculum \u00a9 NoPlaceLeft Academy. The manuals grant permission "
    "for this publication to be used for discipleship purposes.")

with open("/home/hatch/workspace/field-agent/curriculum/curriculum.json", "w") as f:
    json.dump(curriculum, f, ensure_ascii=False, indent=1)
print("wrote curriculum.json", len(json.dumps(curriculum)), "chars")
