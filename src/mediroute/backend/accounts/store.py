"""User accounts and saved request history in one SQLite file (docs/design/user_history.md).

Kept deliberately small for an academic project: email + password (salted scrypt hash), a random
session token (only its SHA-256 is stored), a shortlist of up to 3 hospitals per saved search, and
automatic deletion after RETENTION_DAYS. No report text is ever stored.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from mediroute.utils.paths import APP_DB_FILE, HOSPITALS_FILE

SESSION_DAYS = 7
RETENTION_DAYS = 90
MAX_HOSPITALS = 3
MAX_FAILED_LOGINS = 5
FAILED_LOGIN_WINDOW_MIN = 15
MIN_PASSWORD = 8
MAX_PASSWORD = 128
MAX_TEXT = 4000
MAX_THREAD_ITEMS = 10
MAX_THREAD_TEXT = 500

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT,
    country TEXT NOT NULL,
    language TEXT,
    consent_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_failures (
    email TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    workflow_id TEXT,
    trace_request_id TEXT,
    request_text TEXT,
    city TEXT,
    language TEXT,
    specialty TEXT,
    specialty_reason TEXT,
    thread TEXT NOT NULL DEFAULT '[]',
    hospitals TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_saved_user ON saved_requests(user_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_failures_email ON login_failures(email, at);
"""


class AccountError(Exception):
    """A user-facing problem (bad input, wrong password, ...) with an HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


# ------------------------------------------------------------------ passwords and tokens
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=len(digest_hex) // 2)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ hospital snapshot (server data, not the browser's)
@lru_cache(maxsize=1)
def _hospitals() -> dict[str, dict]:
    if not Path(HOSPITALS_FILE).exists():
        return {}
    with open(HOSPITALS_FILE, encoding="utf-8", newline="") as f:
        return {row["hospital_id"].strip(): row for row in csv.DictReader(f) if (row.get("hospital_id") or "").strip()}


def hospital_snapshot(hospital_id: str, related_specialty: str | None = None) -> dict:
    row = _hospitals().get(str(hospital_id).strip())
    if not row:
        raise AccountError("Unknown hospital.", 404)
    specialties = [s.strip() for col in ("verified_specialties", "team_claimed_specialties")
                   for s in (row.get(col) or "").split(";") if s.strip() and s.strip() != "NA"]
    return {
        "hospital_id": row["hospital_id"].strip(),
        "name": (row.get("hospital_name") or "").strip(),
        "city": (row.get("city") or "").strip(),
        "state": (row.get("state") or "").strip(),
        "specialties": list(dict.fromkeys(specialties)),
        "website": (row.get("official_source_url") or "").strip(),
        "international_page": (row.get("url_Internantional_patients") or "").strip(),
        "related_specialty": (related_specialty or "").strip()[:80] or None,
        "saved_at": _iso(_now()),
    }


def _clip(value, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _clean_thread(thread) -> list[dict]:
    out = []
    for item in (thread or [])[:MAX_THREAD_ITEMS]:
        if not isinstance(item, dict):
            continue
        q, a = _clip(item.get("question"), MAX_THREAD_TEXT), _clip(item.get("answer"), MAX_THREAD_TEXT)
        if q or a:
            out.append({"question": q or "", "answer": a or ""})
    return out


class AccountStore:
    def __init__(self, path: Path | str = APP_DB_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        """One connection per call: committed when the block ends normally, rolled back on an error,
        always closed."""
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    # -------------------------------------------------------------- users
    def signup(self, email: str, password: str, country: str, consent: bool,
               name: str | None = None, language: str | None = None) -> dict:
        email = (email or "").strip().lower()
        if not EMAIL_RE.match(email):
            raise AccountError("Please enter a valid email address.")
        if not (MIN_PASSWORD <= len(password or "") <= MAX_PASSWORD):
            raise AccountError(f"The password needs at least {MIN_PASSWORD} characters.")
        country = _clip(country, 60)
        if not country:
            raise AccountError("Please choose your country of residence.")
        if not consent:
            raise AccountError("Please agree to how your saved searches are stored.")
        now = _iso(_now())
        with self._lock, self._conn() as db:
            if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                raise AccountError("An account with this email already exists. Please log in.", 409)
            cur = db.execute(
                "INSERT INTO users (email, password_hash, name, country, language, consent_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (email, hash_password(password), _clip(name, 80), country, _clip(language, 40), now, now))
            return self._user(db, cur.lastrowid)

    def login(self, email: str, password: str) -> dict:
        email = (email or "").strip().lower()
        since = _iso(_now() - timedelta(minutes=FAILED_LOGIN_WINDOW_MIN))
        with self._lock, self._conn() as db:
            failures = db.execute("SELECT COUNT(*) FROM login_failures WHERE email = ? AND at >= ?",
                                  (email, since)).fetchone()[0]
            if failures >= MAX_FAILED_LOGINS:
                raise AccountError(f"Too many failed attempts. Please wait {FAILED_LOGIN_WINDOW_MIN} minutes.", 429)
            row = db.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
            if not row or not verify_password(password or "", row["password_hash"]):
                db.execute("INSERT INTO login_failures (email, at) VALUES (?, ?)", (email, _iso(_now())))
                db.commit()  # keep the failure even though an error follows
                raise AccountError("Email or password is not correct.", 401)
            db.execute("DELETE FROM login_failures WHERE email = ?", (email,))
            return self._user(db, row["id"])

    def delete_user(self, user_id: int) -> None:
        with self._lock, self._conn() as db:
            db.execute("DELETE FROM saved_requests WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))

    @staticmethod
    def _user(db, user_id: int) -> dict:
        row = db.execute("SELECT id, email, name, country, language, created_at FROM users WHERE id = ?",
                         (user_id,)).fetchone()
        return dict(row) if row else {}

    # -------------------------------------------------------------- sessions
    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock, self._conn() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(_now()),))
            db.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                       (_token_hash(token), user_id, _iso(_now() + timedelta(days=SESSION_DAYS))))
        return token

    def user_for_token(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self._conn() as db:
            row = db.execute("SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at >= ?",
                             (_token_hash(token), _iso(_now()))).fetchone()
            return self._user(db, row["user_id"]) if row else None

    def end_session(self, token: str | None) -> None:
        if token:
            with self._lock, self._conn() as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    # -------------------------------------------------------------- history
    def purge_old(self) -> int:
        cutoff = _iso(_now() - timedelta(days=RETENTION_DAYS))
        with self._lock, self._conn() as db:
            return db.execute("DELETE FROM saved_requests WHERE updated_at < ?", (cutoff,)).rowcount

    def save(self, user_id: int, entry: dict) -> dict:
        """Save one search with one hospital; the same search (workflow id) adds to its shortlist."""
        hospital = hospital_snapshot(entry.get("hospital_id"), entry.get("related_specialty"))
        workflow_id = _clip(entry.get("workflow_id"), 64)
        now = _iso(_now())
        with self._lock, self._conn() as db:
            row = None
            if workflow_id:
                row = db.execute("SELECT * FROM saved_requests WHERE user_id = ? AND workflow_id = ?",
                                 (user_id, workflow_id)).fetchone()
            if row:
                hospitals = json.loads(row["hospitals"])
                if any(h["hospital_id"] == hospital["hospital_id"] for h in hospitals):
                    return self._entry(db, user_id, row["id"])
                if len(hospitals) >= MAX_HOSPITALS:
                    raise AccountError(f"You can keep up to {MAX_HOSPITALS} hospitals per search. "
                                       "Remove one in My history first.", 409)
                hospitals.append(hospital)
                db.execute("UPDATE saved_requests SET hospitals = ?, updated_at = ? WHERE id = ?",
                           (json.dumps(hospitals), now, row["id"]))
                return self._entry(db, user_id, row["id"])
            cur = db.execute(
                "INSERT INTO saved_requests (user_id, created_at, updated_at, workflow_id, trace_request_id, "
                "request_text, city, language, specialty, specialty_reason, thread, hospitals) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, now, now, workflow_id, _clip(entry.get("trace_request_id"), 64),
                 _clip(entry.get("request_text"), MAX_TEXT) if entry.get("save_description", True) else None,
                 _clip(entry.get("city"), 80), _clip(entry.get("language"), 40), _clip(entry.get("specialty"), 80),
                 _clip(entry.get("specialty_reason"), 600), json.dumps(_clean_thread(entry.get("thread"))),
                 json.dumps([hospital])))
            return self._entry(db, user_id, cur.lastrowid)

    def list_entries(self, user_id: int) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT * FROM saved_requests WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
                              (user_id,)).fetchall()
        out = []
        for row in rows:
            hospitals = json.loads(row["hospitals"])
            out.append({"id": row["id"], "created_at": row["created_at"], "updated_at": row["updated_at"],
                        "request_text": row["request_text"], "city": row["city"], "specialty": row["specialty"],
                        "hospitals": [{"hospital_id": h["hospital_id"], "name": h["name"], "city": h["city"]}
                                      for h in hospitals]})
        return out

    def get(self, user_id: int, entry_id: int) -> dict:
        with self._conn() as db:
            return self._entry(db, user_id, entry_id)

    def delete(self, user_id: int, entry_id: int) -> None:
        with self._lock, self._conn() as db:
            if not db.execute("DELETE FROM saved_requests WHERE id = ? AND user_id = ?", (entry_id, user_id)).rowcount:
                raise AccountError("Not found.", 404)

    def remove_hospital(self, user_id: int, entry_id: int, hospital_id: str) -> dict:
        with self._lock, self._conn() as db:
            row = db.execute("SELECT hospitals FROM saved_requests WHERE id = ? AND user_id = ?",
                             (entry_id, user_id)).fetchone()
            if not row:
                raise AccountError("Not found.", 404)
            hospitals = [h for h in json.loads(row["hospitals"]) if h["hospital_id"] != str(hospital_id)]
            if not hospitals:  # the last hospital removed: the entry goes too
                db.execute("DELETE FROM saved_requests WHERE id = ?", (entry_id,))
                return {}
            db.execute("UPDATE saved_requests SET hospitals = ?, updated_at = ? WHERE id = ?",
                       (json.dumps(hospitals), _iso(_now()), entry_id))
            return self._entry(db, user_id, entry_id)

    @staticmethod
    def _entry(db, user_id: int, entry_id: int) -> dict:
        row = db.execute("SELECT * FROM saved_requests WHERE id = ? AND user_id = ?", (entry_id, user_id)).fetchone()
        if not row:  # another user's entry looks exactly like a missing one
            raise AccountError("Not found.", 404)
        out = dict(row)
        out.pop("user_id", None)
        out["thread"] = json.loads(out["thread"])
        out["hospitals"] = json.loads(out["hospitals"])
        return out


_store: AccountStore | None = None


def get_store() -> AccountStore:
    global _store
    if _store is None:
        _store = AccountStore()
    return _store


def set_store(store: AccountStore | None) -> None:
    """Tests: use a store on a temporary file."""
    global _store
    _store = store
