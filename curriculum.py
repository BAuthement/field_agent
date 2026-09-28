"""Loads the parsed NPL Academy curriculum."""
import json
import os

_BASE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_BASE, "curriculum", "curriculum.json")
_QUIZ_PATH = os.path.join(_BASE, "curriculum", "quizzes.json")
_GATE_PATH = os.path.join(_BASE, "curriculum", "gates.json")
_curriculum = None
_quizzes = None
_gates = None


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
