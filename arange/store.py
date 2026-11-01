"""SQLite persistence: users, sessions, attempts, messages, progress."""
import contextlib
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid

from . import config

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY,
  handle TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  settings TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts(
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  lesson_id TEXT NOT NULL,
  level TEXT NOT NULL,
  seed INTEGER NOT NULL,
  world TEXT NOT NULL,
  trace TEXT NOT NULL DEFAULT '[]',
  turns INTEGER NOT NULL DEFAULT 0,
  doc_text TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_user_lesson ON attempts(user_id, lesson_id, created_at DESC);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_attempt ON messages(attempt_id, id);
CREATE TABLE IF NOT EXISTS progress(
  user_id TEXT NOT NULL,
  lesson_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  completed_at INTEGER NOT NULL,
  PRIMARY KEY(user_id, lesson_id, task_id)
);
CREATE TABLE IF NOT EXISTS lesson_stats(
  user_id TEXT NOT NULL,
  lesson_id TEXT NOT NULL,
  hints_used INTEGER NOT NULL DEFAULT 0,
  solution_used INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(user_id, lesson_id)
);
"""


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path=None):
        self.path = str(path or config.DB_PATH)
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript(SCHEMA)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ---- users & sessions -------------------------------------------------
    def create_user(self, handle="guest"):
        user_id = "u_" + uuid.uuid4().hex[:16]
        now = int(time.time())
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO users(id, handle, created_at) VALUES(?,?,?)",
                (user_id, handle, now),
            )
        return {"id": user_id, "handle": handle, "created_at": now}

    def get_user(self, user_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def create_session(self, user_id):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES(?,?,?,?)",
                (_digest(token), user_id, now, now + config.SESSION_TTL),
            )
        return token

    def user_for_session(self, token):
        if not token:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.expires_at>?",
                (_digest(token), int(time.time())),
            ).fetchone()
        return dict(row) if row else None

    # ---- attempts ---------------------------------------------------------
    def create_attempt(self, user_id, lesson_id, level, world, doc_text=None):
        attempt_id = "a_" + uuid.uuid4().hex[:16]
        now = int(time.time())
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO attempts(id,user_id,lesson_id,level,seed,world,doc_text,created_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    user_id,
                    lesson_id,
                    level,
                    secrets.randbelow(2**31 - 1),
                    json.dumps(world, ensure_ascii=False),
                    doc_text,
                    now,
                    now + config.ATTEMPT_TTL,
                ),
            )
        return self.get_attempt(attempt_id)

    def get_attempt(self, attempt_id, user_id=None):
        with self.connect() as db:
            row = db.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        if user_id is not None and data["user_id"] != user_id:
            return None
        if data["expires_at"] <= int(time.time()):
            with self.lock, self.connect() as db:
                db.execute("DELETE FROM messages WHERE attempt_id=?", (attempt_id,))
                db.execute("DELETE FROM attempts WHERE id=?", (attempt_id,))
            return None
        data["world"] = json.loads(data["world"] or "{}")
        data["trace"] = json.loads(data["trace"] or "[]")
        return data

    def latest_attempt(self, user_id, lesson_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT id FROM attempts WHERE user_id=? AND lesson_id=? AND expires_at>? "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id, lesson_id, int(time.time())),
            ).fetchone()
        return self.get_attempt(row["id"], user_id) if row else None

    def save_turn(self, attempt_id, world, trace, turns):
        trace = trace[-240:]
        with self.lock, self.connect() as db:
            db.execute(
                "UPDATE attempts SET world=?, trace=?, turns=?, status='active' WHERE id=?",
                (json.dumps(world, ensure_ascii=False), json.dumps(trace, ensure_ascii=False), turns, attempt_id),
            )

    def reset_attempt(self, attempt_id, world, level):
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM messages WHERE attempt_id=?", (attempt_id,))
            db.execute(
                "UPDATE attempts SET world=?, trace='[]', turns=0, level=?, status='active' WHERE id=?",
                (json.dumps(world, ensure_ascii=False), level, attempt_id),
            )

    def delete_attempt(self, attempt_id, user_id):
        with self.lock, self.connect() as db:
            owned = db.execute(
                "SELECT 1 FROM attempts WHERE id=? AND user_id=?", (attempt_id, user_id)
            ).fetchone()
            if not owned:
                return False
            db.execute("DELETE FROM messages WHERE attempt_id=?", (attempt_id,))
            db.execute("DELETE FROM attempts WHERE id=?", (attempt_id,))
        return True

    def purge_expired(self):
        now = int(time.time())
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            expired = [r["id"] for r in db.execute("SELECT id FROM attempts WHERE expires_at<=?", (now,))]
            for attempt_id in expired:
                db.execute("DELETE FROM messages WHERE attempt_id=?", (attempt_id,))
                db.execute("DELETE FROM attempts WHERE id=?", (attempt_id,))
        return len(expired)

    # ---- messages ---------------------------------------------------------
    def add_message(self, attempt_id, role, content, meta=None):
        now = int(time.time())
        with self.lock, self.connect() as db:
            cur = db.execute(
                "INSERT INTO messages(attempt_id,role,content,meta,created_at) VALUES(?,?,?,?,?)",
                (attempt_id, role, content, json.dumps(meta or {}, ensure_ascii=False), now),
            )
            return cur.lastrowid

    def messages(self, attempt_id):
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,role,content,meta,created_at FROM messages WHERE attempt_id=? ORDER BY id",
                (attempt_id,),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["meta"] = json.loads(item["meta"] or "{}")
            out.append(item)
        return out

    # ---- progress ---------------------------------------------------------
    def progress(self, user_id):
        with self.connect() as db:
            rows = db.execute(
                "SELECT lesson_id, task_id, completed_at FROM progress WHERE user_id=?",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def task_done(self, user_id, lesson_id, task_id):
        with self.connect() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM progress WHERE user_id=? AND lesson_id=? AND task_id=?",
                    (user_id, lesson_id, task_id),
                ).fetchone()
            )

    def mark_task(self, user_id, lesson_id, task_id):
        now = int(time.time())
        with self.lock, self.connect() as db:
            cur = db.execute(
                "INSERT OR IGNORE INTO progress(user_id,lesson_id,task_id,completed_at) VALUES(?,?,?,?)",
                (user_id, lesson_id, task_id, now),
            )
            return cur.rowcount > 0

    def stats(self, user_id, lesson_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT hints_used, solution_used FROM lesson_stats WHERE user_id=? AND lesson_id=?",
                (user_id, lesson_id),
            ).fetchone()
        return dict(row) if row else {"hints_used": 0, "solution_used": 0}

    def bump_hint(self, user_id, lesson_id):
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO lesson_stats(user_id,lesson_id,hints_used) VALUES(?,?,1) "
                "ON CONFLICT(user_id,lesson_id) DO UPDATE SET hints_used=hints_used+1",
                (user_id, lesson_id),
            )
        return self.stats(user_id, lesson_id)

    def mark_solution(self, user_id, lesson_id):
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO lesson_stats(user_id,lesson_id,solution_used) VALUES(?,?,1) "
                "ON CONFLICT(user_id,lesson_id) DO UPDATE SET solution_used=1",
                (user_id, lesson_id),
            )
        return self.stats(user_id, lesson_id)
