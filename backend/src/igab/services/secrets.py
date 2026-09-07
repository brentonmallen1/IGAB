"""Secrets at rest: account and routing numbers.

The key is the one bank sync already uses (SIMPLEFIN_ENCRYPTION_KEY) and the
Fernet wrapper is the one in integrations/simplefin/encryption.py — this
module names the second use of it rather than growing a second key. Nothing
here reaches the change log: the account snapshot fields never include the
encrypted columns, so undo can neither restore nor leak a number.
"""

from igab.integrations.simplefin.encryption import (
    SimpleFINKeyMismatch,
    SimpleFINNotConfigured,
    decrypt,
    encrypt,
    key_problem,
)

__all__ = [
    "SimpleFINKeyMismatch",
    "SimpleFINNotConfigured",
    "decrypt",
    "encrypt",
    "key_problem",
    "last4",
]


def last4(number: str) -> str:
    """The masked display's clear part: the final four digits (or characters
    for a short number), the same rule a bank statement uses."""
    digits = "".join(ch for ch in number if ch.isalnum())
    return digits[-4:]
