"""Users, roles, and password hashing.

Separate from `derivatives/` deliberately. Everything in `derivatives/` is
regenerable and git-ignored, and user accounts are neither: losing them is not
"re-run the pipeline", it is "everyone makes a new account and the attribution on
every past decision points at nothing". They live in `var/app.db`, which the
backup script covers.

Attribution is why this exists at all. Once two people use the app, "who approved
this" and "who ran that" are questions the record has to answer, and a free-text
reviewer field cannot: it is a name someone typed, not a person who logged in.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = REPO_ROOT / "var" / "app.db"

# reviewer signs QC. analyst runs recipes. admin manages users and configs.
# Ordered, so a check is "at least this role".
ROLES = ("reviewer", "analyst", "admin")
_RANK = {role: i for i, role in enumerate(ROLES)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    role          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    disabled      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """Raised for any credential or permission failure."""


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str
    role: str
    disabled: bool = False

    def can(self, required: str) -> bool:
        """Roles are ordered, so this asks 'at least'."""
        if self.disabled:
            return False
        return _RANK[self.role] >= _RANK[required]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def hash_password(password: str) -> str:
    """Argon2id. Never store, log, or return a password anywhere."""
    from argon2 import PasswordHasher

    return PasswordHasher().hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError, VerifyMismatchError

    try:
        return PasswordHasher().verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def add_user(
    name: str, email: str, role: str, password: str, db_path: Path | None = None
) -> User:
    if role not in ROLES:
        raise AuthError(f"unknown role {role!r}; valid roles are {list(ROLES)}")
    if not _EMAIL.match(email or ""):
        raise AuthError(f"{email!r} is not a valid email address")
    if len(password) < 12:
        # Length beats complexity rules, and an admin sets these by hand.
        raise AuthError("a password must be at least 12 characters")
    if not name.strip():
        raise AuthError("a user needs a name; attribution is the point of accounts")

    with connect(db_path) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, role, password_hash, created_at) "
                "VALUES (?,?,?,?,?)",
                (name.strip(), email.lower(), role, hash_password(password), _now()),
            )
        except sqlite3.IntegrityError:
            raise AuthError(f"a user with email {email!r} already exists") from None
        return User(int(cur.lastrowid), name.strip(), email.lower(), role)


def get_user(email: str, db_path: Path | None = None) -> User | None:
    with connect(db_path) as conn, closing(
        conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
    ) as cur:
        row = cur.fetchone()
    return _to_user(row) if row else None


def list_users(db_path: Path | None = None) -> list[User]:
    with connect(db_path) as conn, closing(
        conn.execute("SELECT * FROM users ORDER BY name")
    ) as cur:
        return [_to_user(row) for row in cur.fetchall()]


def _to_user(row: sqlite3.Row) -> User:
    return User(row["id"], row["name"], row["email"], row["role"],
                bool(row["disabled"]))


def set_password(email: str, password: str, db_path: Path | None = None) -> None:
    """Admin resets a password from the command line. No self-service flow."""
    if len(password) < 12:
        raise AuthError("a password must be at least 12 characters")
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE email = ?",
            (hash_password(password), email.lower()),
        )
        if cur.rowcount == 0:
            raise AuthError(f"no user with email {email!r}")


def set_role(email: str, role: str, db_path: Path | None = None) -> None:
    if role not in ROLES:
        raise AuthError(f"unknown role {role!r}; valid roles are {list(ROLES)}")
    with connect(db_path) as conn:
        cur = conn.execute("UPDATE users SET role = ? WHERE email = ?",
                           (role, email.lower()))
        if cur.rowcount == 0:
            raise AuthError(f"no user with email {email!r}")


def set_disabled(email: str, disabled: bool, db_path: Path | None = None) -> None:
    """Disable rather than delete: a deleted user orphans every past decision."""
    with connect(db_path) as conn:
        cur = conn.execute("UPDATE users SET disabled = ? WHERE email = ?",
                           (int(disabled), email.lower()))
        if cur.rowcount == 0:
            raise AuthError(f"no user with email {email!r}")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

SESSION_HOURS = 12


def login(email: str, password: str, db_path: Path | None = None) -> str:
    """Return a session token, or raise. The same error either way.

    A different message for "no such user" and "wrong password" tells an attacker
    which emails exist.
    """
    with connect(db_path) as conn, closing(
        conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
    ) as cur:
        row = cur.fetchone()

    if row is None or not verify_password(row["password_hash"], password):
        raise AuthError("invalid email or password")
    if row["disabled"]:
        raise AuthError("this account is disabled")

    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC).timestamp() + SESSION_HOURS * 3600
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (token, row["id"], _now(),
             datetime.fromtimestamp(expires, UTC).isoformat(timespec="seconds")),
        )
    return token


def user_for_token(token: str, db_path: Path | None = None) -> User | None:
    if not token:
        return None
    with connect(db_path) as conn, closing(
        conn.execute(
            "SELECT users.*, sessions.expires_at FROM sessions "
            "JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
            (token,),
        )
    ) as cur:
        row = cur.fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
        logout(token, db_path)
        return None
    return _to_user(row)


def logout(token: str, db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def purge_expired(db_path: Path | None = None) -> int:
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
        return cur.rowcount
