from typing import Final

from cryptography.fernet import Fernet, InvalidToken

from igab.config import settings
from igab.domain.exceptions import IGABError

#: The only command that produces a key this module accepts. Quoted in the
#: config endpoint the UI reads and in .env.example — a key made any other way
#: (notably `openssl rand -hex 32`, the recipe next door for SECRET_KEY) is not
#: a valid Fernet key, and that mistake is otherwise indistinguishable from a
#: bad setup token.
GENERATE_KEY_COMMAND: Final = (
    'python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
)


class SimpleFINNotConfigured(IGABError):
    """The server cannot store bank credentials: SIMPLEFIN_ENCRYPTION_KEY is
    missing, or is set to something Fernet will not accept."""


class SimpleFINKeyMismatch(IGABError):
    """Stored ciphertext cannot be read with the key the server has now — the
    key was rotated or lost after the connection was saved."""


def key_problem() -> str | None:
    """What is wrong with SIMPLEFIN_ENCRYPTION_KEY, or None if nothing is.

    One home for "is bank sync configured". The setup preflight, the config
    endpoint the UI reads, and the sync path all ask this instead of each
    deciding for itself what an unusable key looks like.
    """
    key = settings.SIMPLEFIN_ENCRYPTION_KEY.strip()
    if not key:
        return (
            "SIMPLEFIN_ENCRYPTION_KEY is not set on the server. Bank sync keeps your "
            "SimpleFIN access URL encrypted at rest, so it cannot run without a key."
        )
    try:
        Fernet(key.encode())
    except Exception:
        return (
            "SIMPLEFIN_ENCRYPTION_KEY is set, but it is not a valid Fernet key. It has "
            "to be 32 url-safe base64 bytes — a hex string, such as one from "
            "`openssl rand -hex 32`, will not work."
        )
    return None


def require_configured() -> None:
    """Raise before doing anything an unusable key would waste.

    SimpleFIN setup tokens are single-use: discovering the key is missing
    *after* exchanging one spends the user's token and sends them back for
    another. Call this before the exchange, not after.
    """
    problem = key_problem()
    if problem is not None:
        raise SimpleFINNotConfigured(problem)


def _fernet() -> Fernet:
    require_configured()
    return Fernet(settings.SIMPLEFIN_ENCRYPTION_KEY.strip().encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        # A valid key that cannot open this row means a *different* key wrote
        # it. Saying so is the difference between a fixable problem and an
        # empty error message — str(InvalidToken()) is the empty string.
        raise SimpleFINKeyMismatch(
            "This connection was saved with a different SIMPLEFIN_ENCRYPTION_KEY and can "
            "no longer be decrypted. Restore the original key, or remove the connection "
            "and set it up again."
        ) from exc
