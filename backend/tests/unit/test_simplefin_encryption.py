"""SimpleFIN encryption-key handling: what counts as configured, what each
failure tells the user, and the ordering that keeps a single-use setup token
from being spent on a server that cannot store the result.

The bug this suite pins: a server with no SIMPLEFIN_ENCRYPTION_KEY exchanged
the user's token, failed to encrypt the access URL, and reported "Invalid
setup token" — so the fix looked like "get another token", and every retry
burned a fresh one.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from igab.api.v1.simplefin import _setup_error_message
from igab.config import settings
from igab.integrations.simplefin.encryption import (
    GENERATE_KEY_COMMAND,
    SimpleFINKeyMismatch,
    SimpleFINNotConfigured,
    decrypt,
    encrypt,
    key_problem,
    require_configured,
)
from igab.services.simplefin_service import SimpleFINService

VALID_KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()
# What `openssl rand -hex 32` produces — the recipe .env.example gives for
# SECRET_KEY two sections up, and the most likely wrong thing to paste here.
HEX_KEY = "a" * 64


@pytest.fixture
def with_key(monkeypatch):
    def _set(value: str):
        monkeypatch.setattr(settings, "SIMPLEFIN_ENCRYPTION_KEY", value)

    return _set


# ─── key_problem: one home for "is bank sync configured" ─────────────────────


def test_valid_key_has_no_problem(with_key):
    with_key(VALID_KEY)
    assert key_problem() is None


def test_missing_key_names_the_variable(with_key):
    with_key("")
    problem = key_problem()
    assert problem is not None
    assert "SIMPLEFIN_ENCRYPTION_KEY" in problem


def test_whitespace_only_key_counts_as_missing(with_key):
    with_key("   \n")
    problem = key_problem()
    assert problem is not None
    assert "not set" in problem


def test_hex_key_is_reported_as_the_wrong_kind_of_key(with_key):
    """The distinction that matters: set-but-unusable is not the same
    diagnosis as unset, and pointing at `openssl rand -hex 32` is the whole
    fix for the person who reached for the recipe next door."""
    with_key(HEX_KEY)
    problem = key_problem()
    assert problem is not None
    assert "not a valid Fernet key" in problem
    assert "openssl" in problem


def test_key_pasted_with_surrounding_whitespace_is_accepted(with_key):
    with_key(f"  {VALID_KEY}\n")
    assert key_problem() is None
    assert decrypt(encrypt("https://user:pass@bridge/simplefin")) == (
        "https://user:pass@bridge/simplefin"
    )


def test_generate_key_command_produces_an_acceptable_key(with_key):
    """The advice the API hands out has to work. This asserts the command's
    payload — Fernet.generate_key() — satisfies the same check that rejects
    everything else."""
    assert "Fernet.generate_key()" in GENERATE_KEY_COMMAND
    with_key(Fernet.generate_key().decode())
    assert key_problem() is None


# ─── encrypt / decrypt ───────────────────────────────────────────────────────


def test_round_trip(with_key):
    with_key(VALID_KEY)
    assert decrypt(encrypt("secret-access-url")) == "secret-access-url"


def test_encrypt_without_a_key_raises_the_typed_error(with_key):
    with_key("")
    with pytest.raises(SimpleFINNotConfigured):
        encrypt("secret-access-url")


def test_decrypt_with_a_different_key_says_so(with_key):
    """str(InvalidToken()) is the empty string, which is how this surfaced as
    a blank "Last sync error" in the UI. The message must name the cause and
    both ways out."""
    with_key(VALID_KEY)
    ciphertext = encrypt("secret-access-url")

    with_key(OTHER_KEY)
    with pytest.raises(SimpleFINKeyMismatch) as exc:
        decrypt(ciphertext)

    message = str(exc.value)
    assert message.strip()
    assert "SIMPLEFIN_ENCRYPTION_KEY" in message
    assert "set it up again" in message


def test_require_configured_is_silent_when_the_key_is_good(with_key):
    with_key(VALID_KEY)
    require_configured()


# ─── setup preflight: the token must not be spent ────────────────────────────


def _service_with_recording_client() -> tuple[SimpleFINService, MagicMock]:
    svc = SimpleFINService(
        session=MagicMock(),
        repo=MagicMock(create=AsyncMock()),
        account_repo=MagicMock(),
        txn_repo=MagicMock(),
        txn_service=MagicMock(),
    )
    svc.client = MagicMock(claim_access_url=AsyncMock(return_value="https://u:p@bridge/simplefin"))
    return svc, svc.client


async def test_setup_does_not_claim_the_token_when_the_key_is_missing(with_key):
    with_key("")
    svc, client = _service_with_recording_client()

    with pytest.raises(SimpleFINNotConfigured):
        await svc.setup(uuid.uuid4(), "c2V0dXAtdG9rZW4=")

    client.claim_access_url.assert_not_awaited()
    svc.repo.create.assert_not_awaited()


async def test_setup_does_not_claim_the_token_when_the_key_is_malformed(with_key):
    with_key(HEX_KEY)
    svc, client = _service_with_recording_client()

    with pytest.raises(SimpleFINNotConfigured):
        await svc.setup(uuid.uuid4(), "c2V0dXAtdG9rZW4=")

    client.claim_access_url.assert_not_awaited()


async def test_setup_claims_and_stores_when_configured(with_key):
    with_key(VALID_KEY)
    svc, client = _service_with_recording_client()

    user_id = uuid.uuid4()
    await svc.setup(user_id, "c2V0dXAtdG9rZW4=")

    client.claim_access_url.assert_awaited_once()
    stored = svc.repo.create.await_args.kwargs["access_url_encrypted"]
    assert decrypt(stored) == "https://u:p@bridge/simplefin"


# ─── error copy: never blame the token for the server's missing key ──────────


def test_missing_key_is_not_reported_as_an_invalid_token():
    message = _setup_error_message(SimpleFINNotConfigured("SIMPLEFIN_ENCRYPTION_KEY is not set."))
    assert "Invalid setup token" not in message
    assert "SIMPLEFIN_ENCRYPTION_KEY" in message
    assert "was not used" in message
    assert GENERATE_KEY_COMMAND in message


def test_base64_failure_is_still_reported_as_an_invalid_token():
    message = _setup_error_message(ValueError("Invalid setup token (base64 decode failed): x"))
    assert "Invalid setup token" in message


def test_an_unrelated_value_error_is_no_longer_called_an_invalid_token():
    """The blanket `isinstance(exc, ValueError)` that used to sit in this
    branch is what mislabelled the encryption error."""
    message = _setup_error_message(ValueError("something else entirely"))
    assert "Invalid setup token" not in message
    assert "something else entirely" in message
