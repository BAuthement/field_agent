"""Loads the parsed NPL Academy curriculum."""
import json
import os
import re

_BASE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_BASE, "curriculum", "curriculum.json")
_QUIZ_PATH = os.path.join(_BASE, "curriculum", "quizzes.json")
_GATE_PATH = os.path.join(_BASE, "curriculum", "gates.json")
_SUBJ_PATH = os.path.join(_BASE, "curriculum", "subjective_questions.json")
_INTROIMG_PATH = os.path.join(_BASE, "curriculum", "intro_images.json")
_curriculum = None
_quizzes = None
_gates = None
_subjective = None
_intro_images = None


def get_curriculum():
    global _curriculum
    if _curriculum is None:
        with open(_PATH, encoding="utf-8") as f:
            _curriculum = json.load(f)
    return _curriculum


def get_level(level_id):
    for lvl in get_curriculum()["levels"]:
        if lvl["id"] == level_id:
            return lvl
    return None


def get_lesson(level_id, number):
    lvl = get_level(level_id)
    if not lvl:
        return None
    for les in lvl["lessons"]:
        if les["number"] == number:
            return les
    return None


def next_lesson_for(user_progress):
    """user_progress: set of (level_id, lesson_number). Returns (level, lesson) of first incomplete."""
    for lvl in get_curriculum()["levels"]:
        if not lvl["lessons"]:
            continue
        for les in lvl["lessons"]:
            if (lvl["id"], les["number"]) not in user_progress:
                return lvl, les
    return None, None


def get_quizzes():
    """Returns {lesson_key: [question,...]}. lesson_key is 'level1:3' etc.
    Each question: {q_en, q_es, options_en[3], options_es[3], answer (index of correct in options_*)}.
    """
    global _quizzes
    if _quizzes is None:
        try:
            with open(_QUIZ_PATH, encoding="utf-8") as f:
                _quizzes = json.load(f)
        except FileNotFoundError:
            _quizzes = {}
    return _quizzes


def get_quiz(level_id, number):
    return get_quizzes().get(f"{level_id}:{number}", [])


_ILLUS_PATH = os.path.join(_BASE, "curriculum", "illustrations.json")
_illustrations = None


def get_illustrations():
    """Returns {lesson_key: [{file, caption, alt}, ...]}. lesson_key is 'level1:1' etc.
    Each file path is relative to static/img/."""
    global _illustrations
    if _illustrations is None:
        try:
            with open(_ILLUS_PATH, encoding="utf-8") as f:
                _illustrations = json.load(f)
        except FileNotFoundError:
            _illustrations = {}
    return _illustrations


def get_lesson_illustrations(level_id, number):
    return get_illustrations().get(f"{level_id}:{number}", [])


_STEP_PATH = os.path.join(_BASE, "curriculum", "step_image_placements.json")
_STEP_OVERRIDE_PATH = os.path.join(_BASE, "curriculum", "step_image_overrides.json")
_step_placements = None
_step_overrides = None


# get_step_placements_raw is defined below with cross-lesson moves applied.


def get_step_overrides():
    """Returns {lesson_key: [{image, anchor_text, placement}, ...]}.

    anchor_text is a unique substring of the lesson body. placement is
    "after" (default: image goes right after the step containing the
    anchor) or "before" (image goes right before that step starts).
    Overrides replace the automatic placement for the listed images.
    """
    global _step_overrides
    if _step_overrides is None:
        try:
            with open(_STEP_OVERRIDE_PATH, encoding="utf-8") as f:
                _step_overrides = json.load(f)
        except FileNotFoundError:
            _step_overrides = {}
    return _step_overrides


def _step_end_offset(body, start):
    """Char offset just past the end of the body step containing `start`.

    A step ends at a newline that follows sentence-ending punctuation and
    is followed by a blank line or a new step/section label.
    """
    import re
    step_start = re.compile(r"(\d+\.\s+[A-Z]|[A-Za-z0-9][A-Za-z0-9' +\-–—]{0,40}:|\[)")
    sent_end = re.compile(r"[.?!][)\]\"']?$")
    pos = start
    while True:
        nl = body.find("\n", pos)
        if nl == -1:
            return len(body)
        before = body[max(0, nl - 80):nl].rstrip()
        after = body[nl + 1:nl + 2]
        rest = body[nl + 1:nl + 60]
        if (before and sent_end.search(before)
                and (after == "\n" or step_start.match(rest.lstrip("\n")))):
            return nl + 2 if after == "\n" else nl + 1
        pos = nl + 1


def _step_start_offset(body, pos):
    """Char offset of the start of the line containing `pos`."""
    nl = body.rfind("\n", 0, pos)
    return nl + 1 if nl != -1 else 0


def _find_anchor(body, anchor):
    """Find anchor_text in body, ignoring whitespace differences
    (newlines vs spaces). Returns the original-body offset, or -1."""
    import re
    anchor_norm = re.sub(r"\s+", " ", anchor).strip()
    if not anchor_norm:
        return -1
    # build normalized body with offset map
    norm_chars = []
    norm_to_orig = []
    i = 0
    while i < len(body):
        if body[i].isspace():
            # collapse run of whitespace to single space
            norm_chars.append(" ")
            norm_to_orig.append(i)
            while i < len(body) and body[i].isspace():
                i += 1
        else:
            norm_chars.append(body[i])
            norm_to_orig.append(i)
            i += 1
    nbody = "".join(norm_chars)
    idx = nbody.find(anchor_norm)
    if idx == -1:
        return -1
    return norm_to_orig[idx]


# Images that were extracted under the wrong lesson (page-segment bleed).
# Maps the original image path -> (correct level_id, lesson_number,
# corrected image path). The files have been renamed on disk.
STEP_LESSON_MOVES = {
    "steps/level3-09-step03.png": ("level3", 10, "steps/level3-10-step03.png"),
    "steps/level3-09-step04.png": ("level3", 10, "steps/level3-10-step04.png"),
    "steps/level3-09-step05.png": ("level3", 10, "steps/level3-10-step05.png"),
}


def get_step_placements_raw():
    """Returns {lesson_key: [{image, offset, anchor, status}, ...]} from the auto-mapper,
    with cross-lesson moves applied."""
    global _step_placements
    if _step_placements is None:
        try:
            with open(_STEP_PATH, encoding="utf-8") as f:
                _step_placements = json.load(f)
        except FileNotFoundError:
            _step_placements = {}
        # apply cross-lesson moves (page-segment bleed corrections)
        for old_img, (nlid, nnum, new_img) in STEP_LESSON_MOVES.items():
            for key in list(_step_placements.keys()):
                kept = []
                moved = []
                for p in _step_placements[key]:
                    if p["image"] == old_img:
                        moved.append({"image": new_img, "offset": p["offset"]})
                    else:
                        kept.append(p)
                _step_placements[key] = kept
                if moved:
                    nkey = f"{nlid}:{nnum}"
                    _step_placements.setdefault(nkey, []).extend(moved)
    return _step_placements


def get_step_placements(level_id, number):
    """Returns [{image, offset}, ...] for the lesson, overrides applied,
    in step-filename order with non-decreasing offsets."""
    key = f"{level_id}:{number}"
    les = get_lesson(level_id, number)
    if not les:
        return []
    body = les["body"]
    auto = {p["image"]: p["offset"] for p in get_step_placements_raw().get(key, [])}
    for ov in get_step_overrides().get(key, []):
        img = ov.get("image")
        anchor = (ov.get("anchor_text") or "").strip()
        if not img:
            continue
        if ov.get("placement") == "end":
            # pin to the very end of the lesson body
            auto[img] = len(body)
            continue
        if not anchor:
            continue
        idx = _find_anchor(body, anchor)
        if idx == -1:
            continue
        if ov.get("placement") == "before":
            auto[img] = _step_start_offset(body, idx)
        else:
            auto[img] = _step_end_offset(body, idx)
    placements = [{"image": img, "offset": off} for img, off in auto.items()]
    # Order by step filename (workbook top-to-bottom sequence), then enforce
    # non-decreasing offsets so images never display out of sequence.
    placements.sort(key=lambda p: p["image"])
    last = 0
    for p in placements:
        if p["offset"] < last:
            p["offset"] = last
        last = p["offset"]
    return placements


def get_lesson_body_html(level_id, number, caption, extra_inserts=None):
    """Lesson body with workbook step images interleaved at their mapped
    positions. Returns HTML (text escaped, figures raw).

    extra_inserts: optional list of (offset, html) tuples — e.g. subjective
    response boxes — merged with the image placements in offset order.
    """
    import html as _html
    les = get_lesson(level_id, number)
    if not les:
        return ""
    body = les["body"]
    placements = get_step_placements(level_id, number)
    inserts = [("img", p["offset"],
                '<figure class="step-fig">'
                f'<img src="/static/img/{_html.escape(p["image"])}" '
                f'alt="{_html.escape(caption)}" loading="lazy">'
                f'<figcaption>{_html.escape(caption)}</figcaption>'
                "</figure>")
               for p in placements]
    for img, anchor, alt, cap in get_intro_image_placements(level_id, number):
        off = anchor_start(body, anchor)
        if off == -1:
            continue
        inserts.append(("img", off,
                        '<figure class="step-fig">'
                        f'<img src="/static/img/{_html.escape(img)}" '
                        f'alt="{_html.escape(alt or caption)}" loading="lazy">'
                        + (f'<figcaption>{_html.escape(cap)}</figcaption>' if cap else "")
                        + "</figure>"))
    for off, html in (extra_inserts or []):
        inserts.append(("box", max(0, min(off, len(body))), html))
    inserts.sort(key=lambda x: (x[1], 0 if x[0] == "img" else 1))
    parts = []
    last = 0
    for _, off, html in inserts:
        if off < last:
            off = last
        parts.append(_html.escape(body[last:off]))
        parts.append(html)
        last = off
    parts.append(_html.escape(body[last:]))
    return "".join(parts)


def get_gates():
    """Returns {"2": [item,...], "3": [item,...]} — self-attested level-entry
    prerequisites from the workbooks. Each item: {en, es}."""
    global _gates
    if _gates is None:
        try:
            with open(_GATE_PATH, encoding="utf-8") as f:
                _gates = json.load(f)
        except FileNotFoundError:
            _gates = {}
    return _gates


def gate_key_for(level_id):
    """'level2' -> '2', 'level3' -> '3'; None when the level has no gate."""
    key = level_id.replace("level", "")
    return key if key in get_gates() else None


def prev_level_with_lessons(level_id):
    """The closest earlier level that has lessons (for level-entry gates)."""
    levels = [l for l in get_curriculum()["levels"] if l["lessons"]]
    for i, lvl in enumerate(levels):
        if lvl["id"] == level_id and i > 0:
            return levels[i - 1]
    return None


def prev_lesson_key(level_id, number):
    """Key of the lesson before (level_id, number), crossing level boundaries.
    Returns None for the very first lesson."""
    levels = [l for l in get_curriculum()["levels"] if l["lessons"]]
    for i, lvl in enumerate(levels):
        if lvl["id"] != level_id:
            continue
        nums = [les["number"] for les in lvl["lessons"]]
        if number in nums:
            idx = nums.index(number)
            if idx > 0:
                return lvl["id"], nums[idx - 1]
            if i > 0:
                pl = levels[i - 1]
                return pl["id"], pl["lessons"][-1]["number"]
        return None
    return None


def split_lookback(level_id, number):
    """Split a lesson body into (lookback_text, rest). lookback_text is None
    when the lesson has no Look Back section (e.g. Introduction pages)."""
    les = get_lesson(level_id, number)
    if not les:
        return None, ""
    body = les["body"]
    idx = body.find("\nLook Up:")
    if body.lstrip().startswith("Look Back:") and idx != -1:
        return body[:idx], body[idx + 1:]
    return None, body


def anchor_start(body, anchor):
    """Start offset of anchor within body, tolerating whitespace differences.
    Returns -1 when not found."""
    words = anchor.split()
    if not words:
        return -1
    pat = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pat, body)
    return m.start() if m else -1


def anchor_end(body, anchor):
    """End offset of anchor within body, tolerating whitespace differences.
    Returns -1 when not found."""
    words = anchor.split()
    if not words:
        return -1
    pat = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pat, body)
    return m.end() if m else -1


def get_subjective_questions():
    """All subjective response questions, keyed 'level_id:number'."""
    global _subjective
    if _subjective is None:
        try:
            with open(_SUBJ_PATH, encoding="utf-8") as f:
                _subjective = json.load(f)
        except FileNotFoundError:
            _subjective = {}
    return _subjective


def get_subjective_for(level_id, number):
    return get_subjective_questions().get(f"{level_id}:{number}", [])


def get_intro_image_placements(level_id, number):
    """[(image_filename, anchor_text), ...] for Introduction pages."""
    global _intro_images
    if _intro_images is None:
        try:
            with open(_INTROIMG_PATH, encoding="utf-8") as f:
                _intro_images = json.load(f)
        except FileNotFoundError:
            _intro_images = {}
    return [(p["image"], p["anchor"], p.get("alt", ""), p.get("caption", ""))
            for p in _intro_images.get(f"{level_id}:{number}", [])]
