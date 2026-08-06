import hashlib
import hmac
import secrets
import time
from threading import Lock

from cryptography.fernet import Fernet

from app.config import FERNET_KEY, PARTNER_API_KEY

_fernet = None


def check_partner_key(header_value: str | None) -> bool:
    """Auth for /api/partner/* — a shared key, not a login session.

    Fails closed: an unset PARTNER_API_KEY rejects every request rather than
    accepting every request, which is what comparing against "" would do.
    """
    if not PARTNER_API_KEY or not header_value:
        return False
    return hmac.compare_digest(header_value, PARTNER_API_KEY)


def _get_fernet():
    global _fernet
    if _fernet is None:
        if not FERNET_KEY:
            raise RuntimeError("FERNET_KEY env var is not set")
        _fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)
    return _fernet


def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


PBKDF2_ITERATIONS = 260000
SESSION_TTL_SECONDS = 12 * 3600


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


_sessions: dict[str, float] = {}
_sessions_lock = Lock()


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[token] = time.time() + SESSION_TTL_SECONDS
    return token


def validate_session(token: str) -> bool:
    with _sessions_lock:
        expiry = _sessions.get(token)
        if expiry is None:
            return False
        if expiry < time.time():
            del _sessions[token]
            return False
        _sessions[token] = time.time() + SESSION_TTL_SECONDS
        return True


def destroy_session(token: str):
    with _sessions_lock:
        _sessions.pop(token, None)
