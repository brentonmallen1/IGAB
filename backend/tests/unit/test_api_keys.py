"""Issuing and recognising read-only API keys.

The parts that are pure: what a key looks like, what is stored, and which
door a given bearer belongs to.
"""

from igab.services.api_key_service import (
    KEY_PREFIX,
    PREFIX_LENGTH,
    generate,
    hash_key,
    looks_like_api_key,
)


class TestGenerate:
    def test_only_the_hash_is_ever_stored(self):
        """The key itself is returned once and never again — the server keeps
        a hash, exactly as it does for a password."""
        raw, prefix, hashed = generate()
        assert hashed == hash_key(raw)
        assert raw not in hashed
        assert len(hashed) == 64

    def test_the_prefix_identifies_without_reconstructing(self):
        """Enough to tell two keys apart in a list, far too little to rebuild
        one."""
        raw, prefix, _ = generate()
        assert raw.startswith(prefix)
        assert len(prefix) == PREFIX_LENGTH
        assert len(prefix) < len(raw) / 2

    def test_every_key_is_different(self):
        keys = {generate()[0] for _ in range(50)}
        assert len(keys) == 50

    def test_a_key_says_where_it_came_from(self):
        raw, _, _ = generate()
        assert raw.startswith(KEY_PREFIX)


class TestWhichDoor:
    def test_a_key_is_recognised(self):
        assert looks_like_api_key(generate()[0])

    def test_a_session_token_is_not(self):
        """The cross-rejection both doors use. Without it a key handed to the
        REST API fails as an 'invalid token' — true, useless, and exactly the
        answer that costs an evening."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.signature"
        assert not looks_like_api_key(jwt)

    def test_nonsense_is_not(self):
        assert not looks_like_api_key("")
        assert not looks_like_api_key("Bearer igab_something")


class TestHashing:
    def test_the_same_key_always_hashes_the_same(self):
        raw, _, _ = generate()
        assert hash_key(raw) == hash_key(raw)

    def test_a_different_key_hashes_differently(self):
        assert hash_key(generate()[0]) != hash_key(generate()[0])
