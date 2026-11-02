"""Password hashing, opaque tokens and a small login throttle — stdlib only.

Passwords: scrypt (n=2^15, r=8, p=1) with a per-user salt, stored as
`scrypt$n$r$p$salt_hex$hash_hex`. Sessions, invites and API keys are random
tokens; only their SHA-256 is stored, so a leaked database cannot be replayed.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque

_N, _R, _P = 2**15, 8, 1
_MAXMEM = 64 * 1024 * 1024

MIN_PASSWORD_LEN = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM
    )
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt_hex),
        n=int(n), r=int(r), p=int(p), maxmem=_MAXMEM,
    )
    return hmac.compare_digest(digest.hex(), hash_hex)


# A constant hash to verify against when the email is unknown, so login time
# does not reveal which emails have accounts.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_api_key() -> tuple[str, str]:
    """Returns (full_key, display_prefix). The full key is shown exactly once."""
    key = "hg_live_" + secrets.token_urlsafe(30)
    return key, key[:14]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:40] or "workspace"


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Throttle:
    """At most `limit` attempts per key in a sliding `window` seconds."""

    def __init__(self, limit: int = 8, window: float = 300.0) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        t = time.monotonic()
        hits = self._hits[key]
        while hits and t - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(t)
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
