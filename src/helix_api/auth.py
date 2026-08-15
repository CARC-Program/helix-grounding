"""
API key authentication.

This replaces a simulated ECDSA secure-element flow. That code worked, but it
modelled an ATECC608B on a hardware terminal that was cut from the project —
so it described a security posture that did not exist, which is worse than a
simpler scheme that describes itself accurately.

What is here is ordinary and deployable: bearer keys, hashed at rest,
compared in constant time, revocable.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

KEY_PREFIX = "helix_sk_"
_PREVIEW_CHARS = 6


def _hash(key: str) -> str:
    """Keys are stored hashed, never in plaintext.

    The property this buys: a leaked key store is not a leaked set of keys.
    Anyone reading the registry — a backup, a log, a compromised disk — gets
    digests they cannot present as credentials.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedKey:
    """The one moment the plaintext key exists outside the caller's hands.

    ``secret`` is never stored and cannot be recovered. Losing it means
    issuing a new key, which is the correct trade: a system that can show you
    your key again is a system that can show it to someone else.
    """

    key_id: str
    secret: str
    label: str

    @property
    def preview(self) -> str:
        """Safe to log and to show in a UI: enough to identify which key,
        not enough to use one."""
        return f"{self.key_id} ({self.secret[len(KEY_PREFIX):][:_PREVIEW_CHARS]}...)"


@dataclass
class _Record:
    key_id: str
    digest: str
    label: str
    revoked: bool = False


@dataclass
class ApiKeyRegistry:
    """In-memory key store.

    Deliberately in-memory: the project has no database, and inventing one to
    hold three keys would repeat the mistake this module is fixing. Swapping
    the dict for a table is a small change on the day there is a table.
    """

    _by_id: dict[str, _Record] = field(default_factory=dict)

    def issue(self, label: str = "") -> IssuedKey:
        """Mint a key. The plaintext is returned once and never retained."""
        key_id = "key_" + secrets.token_hex(6)
        secret = KEY_PREFIX + secrets.token_urlsafe(32)
        self._by_id[key_id] = _Record(key_id, _hash(secret), label)
        return IssuedKey(key_id=key_id, secret=secret, label=label)

    def revoke(self, key_id: str) -> None:
        """Revocation is permanent. Re-enabling a key that may have leaked is
        never the right recovery — issue a new one."""
        record = self._by_id.get(key_id)
        if record is not None:
            record.revoked = True

    def verify(self, presented: str) -> tuple[bool, str]:
        """Check a presented key. Returns (ok, reason).

        The reason is for the audit log, not for the caller: telling a client
        whether a key is unknown or merely revoked hands an attacker a way to
        enumerate valid key IDs. The HTTP layer collapses every failure into
        one response.
        """
        if not presented or not presented.startswith(KEY_PREFIX):
            return False, "malformed key"

        digest = _hash(presented)
        for record in self._by_id.values():
            # compare_digest, not ==, so the time taken does not depend on how
            # many leading characters matched. Comparing digests rather than
            # raw keys also means a timing signal would leak nothing usable.
            if hmac.compare_digest(record.digest, digest):
                if record.revoked:
                    return False, f"key {record.key_id} is revoked"
                return True, record.key_id
        return False, "unknown key"


def extract_bearer(header_value: str | None) -> str:
    """Pull the credential out of an ``Authorization: Bearer <key>`` header.

    Tolerates a bare key without the scheme, because clients send it that way
    and rejecting it teaches nothing — the key is still checked on its merits.
    """
    if not header_value:
        return ""
    value = header_value.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value
