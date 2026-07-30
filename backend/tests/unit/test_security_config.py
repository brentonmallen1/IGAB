"""Boot-time security guards: the app must refuse to start with default secrets.

A public default SECRET_KEY lets anyone forge a valid HS256 JWT for any user; a
default ADMIN_PASSWORD is a published credential. `_validate_security_config`
fails fast on either so a misconfigured self-host never serves.
"""

import pytest

from igab import main
from igab.main import _validate_security_config

STRONG_KEY = "a" * 64  # 64 hex chars, like `openssl rand -hex 32`
STRONG_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def secure_settings(monkeypatch):
    monkeypatch.setattr(main.settings, "SECRET_KEY", STRONG_KEY)
    monkeypatch.setattr(main.settings, "ADMIN_PASSWORD", STRONG_PASSWORD)


def test_strong_config_boots(secure_settings):
    # Does not raise.
    _validate_security_config()


@pytest.mark.parametrize(
    "bad_key",
    [
        "dev-secret-change-in-production",  # config.py default
        "changeme-generate-with-openssl-rand-hex-32",  # .env.example value
        "",  # unset
        "short",  # < 32 chars
    ],
)
def test_insecure_secret_key_refuses_boot(monkeypatch, bad_key):
    monkeypatch.setattr(main.settings, "SECRET_KEY", bad_key)
    monkeypatch.setattr(main.settings, "ADMIN_PASSWORD", STRONG_PASSWORD)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _validate_security_config()


@pytest.mark.parametrize("bad_password", ["changeme", ""])
def test_insecure_admin_password_refuses_boot(monkeypatch, bad_password):
    monkeypatch.setattr(main.settings, "SECRET_KEY", STRONG_KEY)
    monkeypatch.setattr(main.settings, "ADMIN_PASSWORD", bad_password)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        _validate_security_config()
