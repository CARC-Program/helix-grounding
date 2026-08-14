"""
HELIX NEXUS — Authentication layer, per AUTHENTICATION_SYSTEM.md.

IMPORTANT SCOPE NOTE: this is a SOFTWARE SIMULATION of the secure-element
signing flow, for sandbox testing only. On real MK1 hardware, the private
key is generated on and never leaves the ATECC608B secure element
(MK1_COMPONENT_SELECTION.md) — the element itself performs signing
operations. Here, a software ECDSA keypair stands in for that hardware
so the *verification logic* on the server side can be built and tested
before any physical terminal exists. Do not treat this module as
equivalent to real hardware-backed security — it exists to validate the
server-side half of the flow only.
"""

from dataclasses import dataclass
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature


@dataclass
class TerminalIdentity:
    terminal_id: str
    private_key: object  # ec.EllipticCurvePrivateKey — simulated secure element
    public_key_pem: bytes


def provision_simulated_terminal(terminal_id: str) -> TerminalIdentity:
    """
    Simulates initial terminal provisioning. On real hardware this key is
    generated inside the ATECC608B and the private key never leaves it —
    simulated here in software so the registry/verification logic below
    can be tested without physical hardware.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return TerminalIdentity(terminal_id, private_key, public_key_pem)


def sign_request(private_key, payload: bytes) -> bytes:
    """Simulated equivalent of the secure element signing a request."""
    return private_key.sign(payload, ec.ECDSA(hashes.SHA256()))


class TerminalRegistry:
    """
    Server-side registry of terminal_id -> public key, per
    AUTHENTICATION_SYSTEM.md. Real deployment stores this in Postgres
    (DATABASE_ARCHITECTURE.md); in-memory dict here for sandbox testing.
    """

    def __init__(self):
        self._registry: dict[str, bytes] = {}
        self._revoked: set[str] = set()

    def register(self, terminal_id: str, public_key_pem: bytes) -> None:
        self._registry[terminal_id] = public_key_pem

    def revoke(self, terminal_id: str) -> None:
        """Per AUTHENTICATION_SYSTEM.md Section 4 — lost/stolen terminal
        handling. Revocation is permanent; re-provisioning requires a new
        terminal_id, not un-revoking the old one."""
        self._revoked.add(terminal_id)

    def verify_request(self, terminal_id: str, payload: bytes, signature: bytes) -> tuple[bool, str]:
        if terminal_id in self._revoked:
            return False, "terminal_id has been revoked"
        public_key_pem = self._registry.get(terminal_id)
        if public_key_pem is None:
            return False, "unknown terminal_id"

        public_key = serialization.load_pem_public_key(public_key_pem)
        try:
            public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
            return True, "ok"
        except InvalidSignature:
            return False, "invalid signature"
