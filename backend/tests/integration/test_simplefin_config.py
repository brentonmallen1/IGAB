"""The endpoint the UI asks before offering the setup form, and the status the
setup route returns when the server cannot store credentials.

Why this exists: a server with no SIMPLEFIN_ENCRYPTION_KEY used to exchange
the user's single-use setup token, fail to encrypt the result, and answer 400
"Invalid setup token" — so the obvious next step was to fetch another token
and burn that one too.
"""

import pytest
from cryptography.fernet import Fernet

from igab.config import settings

VALID_KEY = Fernet.generate_key().decode()


@pytest.fixture
def with_key(monkeypatch):
    def _set(value: str):
        monkeypatch.setattr(settings, "SIMPLEFIN_ENCRYPTION_KEY", value)

    return _set


async def test_config_reports_a_missing_key(api_client, with_key):
    with_key("")
    resp = await api_client.get("/api/v1/simplefin/config")
    assert resp.status_code == 200

    body = resp.json()
    assert body["configured"] is False
    assert "SIMPLEFIN_ENCRYPTION_KEY" in body["problem"]
    # The fix is served, not hard-coded in the frontend.
    assert "Fernet.generate_key()" in body["generate_key_command"]


async def test_config_reports_a_usable_key(api_client, with_key):
    with_key(VALID_KEY)
    resp = await api_client.get("/api/v1/simplefin/config")
    assert resp.status_code == 200

    body = resp.json()
    assert body["configured"] is True
    assert body["problem"] is None


async def test_setup_without_a_key_is_503_and_does_not_blame_the_token(api_client, with_key):
    with_key("")
    resp = await api_client.post(
        "/api/v1/simplefin/setup",
        json={"setup_token": "aHR0cHM6Ly9leGFtcGxlLmludmFsaWQvY2xhaW0="},
    )

    # 503, not 400: the server is not ready, the request was not wrong.
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "Invalid setup token" not in detail
    assert "SIMPLEFIN_ENCRYPTION_KEY" in detail
    assert "was not used" in detail
