"""Runtime configuration and instance paths.

Everything is local by default. The data directory holds the SQLite database,
the per-instance HMAC secret used for canaries, and nothing else.
"""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AR_RANGE_DATA", str(ROOT / ".range"))).resolve()
DB_PATH = DATA_DIR / "range.sqlite3"
SECRET_PATH = DATA_DIR / "instance_secret"
LESSONS_DIR = ROOT / "lessons"
WEB_DIR = ROOT / "web"

SESSION_COOKIE = "ar_session"
SESSION_TTL = 60 * 60 * 24 * 30
ATTEMPT_TTL = 60 * 60 * 24
MAX_BODY = 256 * 1024
MAX_MESSAGE = 4000
MAX_DOC = 8000
MAX_TURNS = 40

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

# Only enable when the UI is intentionally embedded (e.g. a preview proxy).
ALLOW_EMBED = os.environ.get("AR_RANGE_ALLOW_EMBED") == "1"


def instance_secret():
    """A stable per-instance secret so canaries survive restarts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        value = SECRET_PATH.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    value = secrets.token_hex(32)
    SECRET_PATH.write_text(value, encoding="utf-8")
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass
    return value
