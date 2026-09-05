"""The SimpleFIN bridge client — the boundary where untrusted bank data arrives.

This file was at 21.6% coverage, the lowest in the backend, and it is the one
module in it that parses a third party's JSON. Everything downstream — the
ledger, the reserve, every card figure — is built on what `get_feed` returns,
and the two defects this integration has produced (a first sync thousands short
of the bank's own balance, and cross-account transfer legs that were never
paired) both entered as data this function handed on without comment.

So the cases here are mostly about a response that is not what the docs
promise: a missing key, a balance that will not parse, an account with no id.
The client's job at that boundary is to be boring — skip what it cannot read,
keep what it can, and never invent a number.

Fixtures are invented (`bridge.example.test`, `Harborstone`) per the
personal-data rule; no captured response is committed here.
"""

import base64
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from igab.integrations.simplefin.client import (
    SimpleFINClient,
    SimpleFINFeed,
    _extract_auth,
)

BRIDGE = "https://bridge.example.test"
ACCESS = "https://user:secret@bridge.example.test/simplefin"
ACCOUNTS_URL = f"{BRIDGE}/simplefin/accounts"
D = Decimal


@pytest.fixture
def client() -> SimpleFINClient:
    return SimpleFINClient()


class TestExtractAuth:
    """Credentials come embedded in the access URL and have to be pulled out:
    httpx does not always forward them across a redirect, so they are passed
    explicitly instead. The bare URL it returns is what every request is built
    on, so a mistake here sends the credentials nowhere or the request to the
    wrong host."""

    def test_splits_credentials_from_the_url(self):
        bare, auth = _extract_auth(ACCESS)
        assert bare == "https://bridge.example.test/simplefin"
        assert auth == ("user", "secret")
        assert "secret" not in bare, "the password must not survive into the request URL"

    def test_keeps_a_non_default_port(self):
        bare, auth = _extract_auth("https://user:secret@bridge.example.test:8443/simplefin")
        assert bare == "https://bridge.example.test:8443/simplefin"
        assert auth == ("user", "secret")

    def test_a_url_with_no_credentials_yields_empty_strings(self):
        """Not an error here. The request goes out unauthenticated and the
        bridge rejects it, which is a clearer failure than raising on a URL
        the user may have pasted without its credentials."""
        bare, auth = _extract_auth(f"{BRIDGE}/simplefin")
        assert bare == f"{BRIDGE}/simplefin"
        assert auth == ("", "")

    def test_a_username_with_no_password(self):
        bare, auth = _extract_auth("https://user@bridge.example.test/simplefin")
        assert bare == f"{BRIDGE}/simplefin"
        assert auth == ("user", "")


class TestClaimAccessURL:
    """The one-time exchange of a setup token for a durable access URL."""

    @staticmethod
    def _token(url: str, *, strip_padding: bool = False) -> str:
        token = base64.urlsafe_b64encode(url.encode()).decode()
        return token.rstrip("=") if strip_padding else token

    @respx.mock
    async def test_posts_to_the_decoded_claim_url_and_returns_the_access_url(self, client):
        claim = f"{BRIDGE}/simplefin/claim/abc123"
        route = respx.post(claim).mock(return_value=httpx.Response(200, text=f"  {ACCESS}  "))
        got = await client.claim_access_url(self._token(claim))
        assert got == ACCESS, "surrounding whitespace must be stripped"
        assert route.called
        # An empty body with an explicit Content-Length: some bridges reject a
        # POST without it.
        assert route.calls[0].request.content == b""
        assert route.calls[0].request.headers["Content-Length"] == "0"

    @respx.mock
    async def test_a_token_stripped_of_its_base64_padding_still_decodes(self, client):
        """Setup tokens get pasted out of emails and web pages, which is where
        the trailing `=` goes missing. The client re-adds it rather than
        failing on a token the user can see is correct."""
        claim = f"{BRIDGE}/simplefin/claim/needs-pad"  # encodes with a trailing "="
        unpadded = self._token(claim, strip_padding=True)
        assert len(unpadded) % 4 != 0, "this fixture is pointless if it is already aligned"
        route = respx.post(claim).mock(return_value=httpx.Response(200, text=ACCESS))
        assert await client.claim_access_url(unpadded) == ACCESS
        assert route.called

    @respx.mock
    async def test_surrounding_whitespace_on_the_token_is_tolerated(self, client):
        claim = f"{BRIDGE}/simplefin/claim/spaced"
        route = respx.post(claim).mock(return_value=httpx.Response(200, text=ACCESS))
        assert await client.claim_access_url(f"\n  {self._token(claim)}  \n") == ACCESS
        assert route.called

    async def test_a_token_that_is_not_base64_raises_before_any_request(self, client):
        """Bytes that are valid base64 but not valid UTF-8 — the shape of a
        mistyped token. It must fail as a ValueError naming the problem, not
        as whatever httpx does with a garbage URL."""
        with pytest.raises(ValueError, match="Invalid setup token"):
            await client.claim_access_url(base64.urlsafe_b64encode(b"\xff\xfe").decode())

    @respx.mock
    async def test_an_http_error_from_the_bridge_propagates(self, client):
        claim = f"{BRIDGE}/simplefin/claim/expired"
        respx.post(claim).mock(return_value=httpx.Response(403, text="token already claimed"))
        with pytest.raises(httpx.HTTPStatusError):
            await client.claim_access_url(self._token(claim))


class TestGetAccounts:
    @respx.mock
    async def test_returns_the_accounts_list_with_credentials_passed_explicitly(self, client):
        route = respx.get(ACCOUNTS_URL).mock(
            return_value=httpx.Response(200, json={"accounts": [{"id": "acc-1"}, {"id": "acc-2"}]})
        )
        assert await client.get_accounts(ACCESS) == [{"id": "acc-1"}, {"id": "acc-2"}]
        request = route.calls[0].request
        assert request.url.params["version"] == "2"
        assert "Authorization" in request.headers

    @respx.mock
    async def test_a_response_with_no_accounts_key_is_an_empty_list(self, client):
        respx.get(ACCOUNTS_URL).mock(return_value=httpx.Response(200, json={}))
        assert await client.get_accounts(ACCESS) == []

    @respx.mock
    async def test_a_trailing_slash_on_the_access_url_does_not_double_up(self, client):
        respx.get(ACCOUNTS_URL).mock(return_value=httpx.Response(200, json={"accounts": []}))
        assert await client.get_accounts(f"{ACCESS}/") == []

    @respx.mock
    async def test_an_http_error_propagates(self, client):
        respx.get(ACCOUNTS_URL).mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_accounts(ACCESS)


class TestGetFeed:
    """One request carries both the window's transactions and each account's
    reported balance. Discarding the balance is what let a first sync ship a
    ledger thousands short of the bank's own figure with nothing anchoring the
    difference — so these pin that both halves survive the parse."""

    @staticmethod
    def _response(accounts: list[dict], **extra) -> httpx.Response:
        return httpx.Response(200, json={"accounts": accounts, **extra})

    @respx.mock
    async def test_transactions_carry_their_account_id_and_balances_come_back(self, client):
        respx.get(ACCOUNTS_URL).mock(
            return_value=self._response(
                [
                    {
                        "id": "acc-1",
                        "balance": "-482.19",
                        "transactions": [{"id": "t1", "amount": "-20.00"}],
                    },
                    {
                        "id": "acc-2",
                        "balance": "1200.00",
                        "transactions": [{"id": "t2", "amount": "40.00"}],
                    },
                ]
            )
        )
        feed = await client.get_feed(ACCESS)
        assert isinstance(feed, SimpleFINFeed)
        assert feed.balances == {"acc-1": D("-482.19"), "acc-2": D("1200.00")}
        # The account id is the only link back — a transaction that loses it
        # cannot be filed to an account at all.
        assert [(t["id"], t["account_id"]) for t in feed.transactions] == [
            ("t1", "acc-1"),
            ("t2", "acc-2"),
        ]

    @respx.mock
    async def test_the_default_window_asks_for_pending_and_no_start_date(self, client):
        route = respx.get(ACCOUNTS_URL).mock(return_value=self._response([]))
        await client.get_feed(ACCESS)
        params = route.calls[0].request.url.params
        assert params["version"] == "2"
        assert params["pending"] == "1"
        assert "start-date" not in params

    @respx.mock
    async def test_since_becomes_a_unix_start_date(self, client):
        route = respx.get(ACCOUNTS_URL).mock(return_value=self._response([]))
        since = datetime(2026, 3, 1, tzinfo=UTC)
        await client.get_feed(ACCESS, since=since)
        assert route.calls[0].request.url.params["start-date"] == str(int(since.timestamp()))

    @respx.mock
    async def test_a_naive_since_is_read_as_utc(self, client):
        """The caller's clock is not the bridge's. A naive datetime is stamped
        UTC rather than the runner's local zone, or the window would slide by
        the host's offset."""
        route = respx.get(ACCOUNTS_URL).mock(return_value=self._response([]))
        await client.get_feed(ACCESS, since=datetime(2026, 3, 1))
        expected = int(datetime(2026, 3, 1, tzinfo=UTC).timestamp())
        assert route.calls[0].request.url.params["start-date"] == str(expected)

    @respx.mock
    async def test_an_unparseable_balance_is_skipped_and_the_rest_survives(self, client):
        """The one that matters: a balance the bridge sends as junk must not
        take the whole sync down, and must not book a wrong number either. It
        is dropped, and the account simply has no reported balance."""
        respx.get(ACCOUNTS_URL).mock(
            return_value=self._response(
                [
                    {"id": "bad", "balance": "not-a-number", "transactions": [{"id": "t1"}]},
                    {"id": "good", "balance": "10.00", "transactions": [{"id": "t2"}]},
                ]
            )
        )
        feed = await client.get_feed(ACCESS)
        assert feed.balances == {"good": D("10.00")}
        # The transactions on the bad account are still returned — a balance we
        # cannot read says nothing about rows we can.
        assert {t["id"] for t in feed.transactions} == {"t1", "t2"}

    @respx.mock
    async def test_a_null_balance_records_nothing_rather_than_zero(self, client):
        """Absent is not zero. Recording 0 here would tell the reconciler the
        bank said the account was empty."""
        respx.get(ACCOUNTS_URL).mock(
            return_value=self._response([{"id": "acc-1", "balance": None, "transactions": []}])
        )
        assert (await client.get_feed(ACCESS)).balances == {}

    @respx.mock
    async def test_an_account_with_no_id_contributes_no_balance(self, client):
        respx.get(ACCOUNTS_URL).mock(
            return_value=self._response([{"balance": "10.00", "transactions": [{"id": "t1"}]}])
        )
        feed = await client.get_feed(ACCESS)
        assert feed.balances == {}
        assert feed.transactions == [{"id": "t1", "account_id": None}]

    @respx.mock
    async def test_an_account_with_no_transactions_key_is_fine(self, client):
        respx.get(ACCOUNTS_URL).mock(
            return_value=self._response([{"id": "acc-1", "balance": "5.00"}])
        )
        feed = await client.get_feed(ACCESS)
        assert feed.transactions == []
        assert feed.balances == {"acc-1": D("5.00")}

    @respx.mock
    async def test_an_errors_list_is_logged_and_usable_data_still_returned(self, client, caplog):
        """SimpleFIN reports per-institution failures in `errors` beside the
        accounts that did work. Dropping the good half would turn one bank's
        outage into a sync that does nothing."""
        respx.get(ACCOUNTS_URL).mock(
            return_value=self._response(
                [{"id": "acc-1", "balance": "5.00", "transactions": [{"id": "t1"}]}],
                errors=["Harborstone: connection expired"],
            )
        )
        with caplog.at_level("WARNING"):
            feed = await client.get_feed(ACCESS)
        assert feed.balances == {"acc-1": D("5.00")}
        assert len(feed.transactions) == 1
        assert "Harborstone: connection expired" in caplog.text

    @respx.mock
    async def test_an_empty_response_is_an_empty_feed(self, client):
        respx.get(ACCOUNTS_URL).mock(return_value=httpx.Response(200, json={}))
        feed = await client.get_feed(ACCESS)
        assert feed.transactions == []
        assert feed.balances == {}

    @respx.mock
    async def test_an_http_error_propagates(self, client):
        respx.get(ACCOUNTS_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_feed(ACCESS)
