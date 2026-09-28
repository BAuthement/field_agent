"""Detect ministry actions described in a user's own words.

When a homework reflection describes sharing the gospel (e.g. "I shared my
testimony", "we drew the 3-Circles"), this module maps that wording to an
activity type and pulls out how many people were reached, so the app can
log it automatically instead of making the user re-enter it by hand.
"""
import re

# Ordered: specific tools first, general gospel-sharing last.
# Each item: (regex, activity_type, i18n label key for the "how many?" prompt).
PATTERNS = [
    (r"3[\s\-]?circles|three circles|3[\s\-]?c[ií]rculos|tres c[ií]rculos",
     "gospel_conversation", "share_circles"),
    (r"testimon(y|io)|my testimony|mi testimonio|15[\s\-]?second",
     "gospel_conversation", "share_testimony"),
    (r"house of peace|persona de paz|hombre de paz",
     "gospel_conversation", "share_hop"),
    (r"shared the gospel|compart[ií] el evangelio|prediqu[ée]|evangeliz",
     "gospel_conversation", "share_gospel"),
    (r"\bgospel\b|\bevangeli\w*\b",
     "gospel_conversation", "share_gospel"),
    (r"3/3|three[\s\-]?thirds|tres tercios",
     "discipleship_meeting", "share_33"),
    (r"follow[\s\-]?up|seguimiento|discipul\w*",
     "discipleship_meeting", "share_discipleship"),
    (r"bapti\w*|bauti\w*",
     "baptism", "share_baptism"),
    (r"prayer walk|caminata de oraci[óo]n|prayed for|or[ée] por|oramos por",
     "prayer", "share_prayer"),
    (r"\bmawl\b|model assist|entren\w*|capacit\w*",
     "training_session", "share_training"),
    (r"church plant|plantaci[óo]n de iglesias?|nueva iglesia",
     "church_plant", "share_church"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), t, l) for p, t, l in PATTERNS]

#: Valid i18n label keys returned by detect_ministry_action.
SHARE_LABELS = frozenset(label for _, _, label in PATTERNS)

_NOUNS = r"people|persons?|personas?|almas?|souls|hermanos?|famil(?:y|ies)|familias?|believers?|creyentes?"
_NUM_WORDS = ("one|two|three|four|five|six|seven|eight|nine|ten|"
              "uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez")
# "3 people", "two new believers", "con 12 personas" — one optional
# adjective allowed between the number and the noun.
_COUNT_RE = re.compile(r"\b(\d{1,4}|" + _NUM_WORDS + r")\s+(?:\w+\s+)?(" + _NOUNS + r")\b",
                       re.IGNORECASE)
_WITH_RE = re.compile(r"\b(?:with|con|para)\s+(\d{1,4})\b", re.IGNORECASE)

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}


def detect_ministry_action(text):
    """Return (activity_type, label_key) for the first ministry action found
    in the text, or None when nothing recognizable is described."""
    if not text:
        return None
    for rx, atype, label in _COMPILED:
        if rx.search(text):
            return atype, label
    return None


def extract_people_count(text):
    """Pull a 'how many people' number out of free text. Returns an int or
    None when no count is stated."""
    if not text:
        return None
    m = _COUNT_RE.search(text)
    if m:
        raw = m.group(1).lower()
        return int(raw) if raw.isdigit() else _WORD_NUMBERS[raw]
    m = _WITH_RE.search(text)
    if m:
        return int(m.group(1))
    return None
