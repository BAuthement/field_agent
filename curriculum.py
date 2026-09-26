"""Loads the parsed NPL Academy curriculum."""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "curriculum", "curriculum.json")
_curriculum = None


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
