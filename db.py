"""Storage for the Field Agent app.

SQLite (zero-config) by default; PostgreSQL when DATABASE_URL is set
(e.g. a free Neon database paired with Render's free tier).
All app code keeps using `?` placeholders -- they are translated to `%s`
for Postgres automatically, and rows behave like dicts on both backends.
"""
import os
import sqlite3
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))

SQLITE_PATH = os.environ.get(
    "FIELD_AGENT_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "field-agent.db"),
)

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    field_location TEXT DEFAULT '',
    language TEXT DEFAULT 'en',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    date TEXT NOT NULL,
    location TEXT DEFAULT '',
    people_count INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    follow_up INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    CHECK (type IN ('gospel_conversation','discipleship_meeting','training_session',
                    'church_plant','baptism','prayer','humanitarian','other'))
);
CREATE TABLE IF NOT EXISTS progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    level_id TEXT NOT NULL,
    lesson_number INTEGER NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, level_id, lesson_number)
);
CREATE INDEX IF NOT EXISTS idx_entries_user_date ON entries(user_id, date);
CREATE TABLE IF NOT EXISTS quiz_done (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    level_id TEXT NOT NULL,
    lesson_number INTEGER NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, level_id, lesson_number)
);
CREATE TABLE IF NOT EXISTS homework_reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    level_id TEXT NOT NULL,
    lesson_number INTEGER NOT NULL,
    did_homework INTEGER NOT NULL DEFAULT 0,
    positive_experience TEXT DEFAULT '',
    improve TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (user_id, level_id, lesson_number)
);
CREATE INDEX IF NOT EXISTS idx_reflections_user ON homework_reflections(user_id);
CREATE TABLE IF NOT EXISTS level_gates (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    level_id TEXT NOT NULL,
    attested_at TEXT NOT NULL,
    PRIMARY KEY (user_id, level_id)
);
CREATE TABLE IF NOT EXISTS subjective_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    level_id TEXT NOT NULL,
    lesson_number INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    answer_text TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, level_id, lesson_number, question_id)
);
CREATE INDEX IF NOT EXISTS idx_subjresp_user ON subjective_responses(user_id);
CREATE TABLE IF NOT EXISTS lookback_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    level_id TEXT NOT NULL,
    lesson_number INTEGER NOT NULL,
    did_homework INTEGER,
    answer_text TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, level_id, lesson_number)
);
CREATE INDEX IF NOT EXISTS idx_lookback_user ON lookback_responses(user_id);
"""

# Same tables, Postgres dialect (SERIAL instead of AUTOINCREMENT).
SCHEMA_PG = SCHEMA_SQLITE.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                                  "SERIAL PRIMARY KEY")


class _Conn:
    """Thin wrapper over a raw DBAPI connection.

    - Translates `?` placeholders to `%s` on Postgres.
    - Rows are dict-like on both backends (sqlite3.Row / RealDictRow).
    """

    def __init__(self, raw, is_pg):
        self._raw = raw
        self._pg = is_pg

    def execute(self, sql, params=()):
        if self._pg:
            sql = sql.replace("?", "%s")
        cur = self._raw.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, sql):
        if self._pg:
            cur = self._raw.cursor()
            for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                cur.execute(stmt)
        else:
            self._raw.executescript(sql)

    def commit(self):
        self._raw.commit()

    def close(self):
        self._raw.close()


def db_kind():
    return "postgres" if USE_PG else "sqlite"


def get_db():
    if USE_PG:
        import psycopg2
        import psycopg2.extras
        raw = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=10,
        )
        return _Conn(raw, True)
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    raw = sqlite3.connect(SQLITE_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return _Conn(raw, False)


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA_PG if USE_PG else SCHEMA_SQLITE)
    _ensure_entry_tracking_columns(conn)
    _migrate_reflections_to_lookback(conn)
    conn.commit()
    conn.close()


def _migrate_reflections_to_lookback(conn):
    """One-time migration: the old 3-part post-lesson homework reflections
    become per-lesson Look Back responses (same lesson number — both reflect
    on the previous lesson's GOAL/homework). Runs only for rows not already
    migrated."""
    rows = conn.execute(
        "SELECT hr.id, hr.user_id, hr.level_id, hr.lesson_number, hr.did_homework,"
        " COALESCE(hr.positive_experience,'') AS pos, COALESCE(hr.improve,'') AS imp,"
        " hr.created_at FROM homework_reflections hr"
        " JOIN users u ON u.id = hr.user_id").fetchall()
    for r in rows:
        rid, uid, lid, num = r["id"], r["user_id"], r["level_id"], r["lesson_number"]
        exists = conn.execute(
            "SELECT id FROM lookback_responses WHERE user_id = ? AND level_id = ?"
            " AND lesson_number = ?", (uid, lid, num)).fetchone()
        if exists:
            lb_id = exists["id"]
        else:
            answer = (r["pos"] or "").strip()
            if (r["imp"] or "").strip():
                answer = (answer + "\n\n" + r["imp"].strip()).strip()
            ts = r["created_at"] or now_iso()
            conn.execute(
                "INSERT INTO lookback_responses (user_id, level_id, lesson_number,"
                " did_homework, answer_text, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (uid, lid, num, r["did_homework"], answer, ts, ts))
            lb_id = conn.execute(
                "SELECT id FROM lookback_responses WHERE user_id = ? AND level_id = ?"
                " AND lesson_number = ?", (uid, lid, num)).fetchone()["id"]
        # Re-link entries auto-logged from the old reflection to the lookback.
        conn.execute("UPDATE entries SET lookback_id = ? WHERE reflection_id = ?",
                     (lb_id, rid))


def _ensure_entry_tracking_columns(conn):
    """Add source/reflection_id to entries on databases created before v2.2.

    source: 'manual' for hand-logged entries, 'reflection' for entries the app
    auto-created from a homework reflection's described experience.
    reflection_id: the homework_reflections row the entry was built from.
    """
    if USE_PG:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'entries'")
        cols = {r["column_name"] for r in rows}
    else:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(entries)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN source TEXT DEFAULT 'manual'")
    if "reflection_id" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN reflection_id INTEGER")
    if "lookback_id" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN lookback_id INTEGER")
    if "subj_question_id" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN subj_question_id TEXT")


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")
