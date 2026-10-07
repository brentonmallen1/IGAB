"""Many splits' lines in one request — the register's "show split lines" view.

`POST /{budget_id}/transactions/split-lines` serves every split on a register
page at once. It is the batch form of `GET /transactions/{id}/splits` and runs
the same loader (`get_splits_for`, which `get_splits` now calls with one id), so
the register and the split editor cannot disagree about a split's lines.
"""

import uuid
from datetime import date
from decimal import Decimal

from igab.api.v1.schemas.transaction import MAX_SPLIT_LINE_PARENTS
from igab.services.transaction_service import SplitSpec

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

TXN_DATE = date(2026, 8, 1)


async def _split(services, budget, account, amounts, *, memo=None):
    txn = await create_transaction(
        services.session, budget, account, str(sum(Decimal(a) for a in amounts)), TXN_DATE
    )
    return await services.transactions.convert_to_split(
        budget.id,
        txn.id,
        [SplitSpec(amount=Decimal(a), memo=memo) for a in amounts],
    )


async def _budget(db_session, user):
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    return budget, account


async def _lines(api_client, budget, *parent_ids):
    return await api_client.post(
        f"/api/v1/{budget.id}/transactions/split-lines",
        json={"parent_ids": [str(p) for p in parent_ids]},
    )


async def test_lines_are_grouped_per_parent_in_loader_order(api_client, db_session):
    budget, account = await _budget(db_session, api_client.test_user)
    services = make_services(db_session)
    first = await _split(services, budget, account, ["-60.00", "-40.00"], memo="food")
    second = await _split(services, budget, account, ["-5.00", "-3.00", "-2.00"])

    got = await _lines(api_client, budget, first.id, second.id)
    assert got.status_code == 200, got.text
    body = got.json()
    assert set(body) == {str(first.id), str(second.id)}
    assert sorted(line["amount"] for line in body[str(first.id)]) == [-60.0, -40.0]
    assert sorted(line["amount"] for line in body[str(second.id)]) == [-5.0, -3.0, -2.0]
    assert all(line["memo"] == "food" for line in body[str(first.id)])
    assert all(line["parent_transaction_id"] == str(first.id) for line in body[str(first.id)])
    # The order is the one-split endpoint's order — (created_at, id) — line
    # for line, because both run one loader.
    for parent in (first, second):
        one = await api_client.get(
            f"/api/v1/transactions/{parent.id}/splits", params={"budget_id": str(budget.id)}
        )
        assert [line["id"] for line in body[str(parent.id)]] == [line["id"] for line in one.json()]


async def test_loader_orders_by_created_at_then_id(db_session):
    user = await create_user(db_session)
    budget, account = await _budget(db_session, user)
    services = make_services(db_session)
    parent = await _split(services, budget, account, ["-1.00", "-2.00", "-3.00", "-4.00"])
    lines = (await services.transaction_repo.get_splits_for([parent.id]))[parent.id]
    assert [c.id for c in lines] == [
        c.id for c in sorted(lines, key=lambda c: (c.created_at, c.id))
    ]
    assert [c.id for c in lines] == [
        c.id for c in await services.transaction_repo.get_splits(parent.id)
    ]


async def test_deleted_lines_are_left_out(api_client, db_session):
    budget, account = await _budget(db_session, api_client.test_user)
    services = make_services(db_session)
    parent = await _split(services, budget, account, ["-60.00", "-40.00"])
    lines = await services.transaction_repo.get_splits(parent.id)
    kept = next(c for c in lines if c.amount == Decimal("-60.00"))
    # Naming one line and omitting the other removes (soft-deletes) it.
    await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [
            SplitSpec(id=kept.id, amount=Decimal("-60.00")),
            SplitSpec(amount=Decimal("-40.00"), memo="fresh"),
        ],
    )
    await db_session.flush()

    body = (await _lines(api_client, budget, parent.id)).json()
    served = body[str(parent.id)]
    assert len(served) == 2
    removed = next(c for c in lines if c.id != kept.id)
    assert str(removed.id) not in {line["id"] for line in served}
    assert any(line["memo"] == "fresh" for line in served)


async def test_another_budgets_parent_ids_answer_nothing(api_client, db_session):
    budget, account = await _budget(db_session, api_client.test_user)
    stranger = await create_user(db_session)
    other_budget, other_account = await _budget(db_session, stranger)
    services = make_services(db_session)
    mine = await _split(services, budget, account, ["-6.00", "-4.00"])
    theirs = await _split(services, other_budget, other_account, ["-9.00", "-1.00"])

    got = await _lines(api_client, budget, mine.id, theirs.id)
    assert got.status_code == 200, got.text
    assert set(got.json()) == {str(mine.id)}, "another budget's split must not leak"

    only_theirs = await _lines(api_client, budget, theirs.id)
    assert only_theirs.status_code == 200 and only_theirs.json() == {}


async def test_an_owned_parent_without_lines_gets_an_empty_list(api_client, db_session):
    budget, account = await _budget(db_session, api_client.test_user)
    plain = await create_transaction(db_session, budget, account, "-12.00", TXN_DATE)
    body = (await _lines(api_client, budget, plain.id)).json()
    assert body == {str(plain.id): []}


async def test_malformed_id_is_422_not_500(api_client, db_session):
    budget, _ = await _budget(db_session, api_client.test_user)
    got = await _lines(api_client, budget, "not-a-uuid")
    assert got.status_code == 422, got.text


async def test_missing_parent_ids_is_422(api_client, db_session):
    budget, _ = await _budget(db_session, api_client.test_user)
    got = await api_client.post(f"/api/v1/{budget.id}/transactions/split-lines", json={})
    assert got.status_code == 422, got.text


async def test_empty_parent_ids_answers_nothing(api_client, db_session):
    budget, _ = await _budget(db_session, api_client.test_user)
    got = await _lines(api_client, budget)
    assert got.status_code == 200 and got.json() == {}


async def test_the_cap_is_allowed_and_one_past_it_is_422(api_client, db_session):
    budget, _ = await _budget(db_session, api_client.test_user)
    at_cap = [uuid.uuid4() for _ in range(MAX_SPLIT_LINE_PARENTS)]
    ok = await _lines(api_client, budget, *at_cap)
    assert ok.status_code == 200 and ok.json() == {}, "unknown ids answer nothing"
    over = await _lines(api_client, budget, *at_cap, uuid.uuid4())
    assert over.status_code == 422, over.text


async def test_another_users_budget_is_refused(api_client, db_session):
    stranger = await create_user(db_session)
    other_budget, _ = await _budget(db_session, stranger)
    got = await _lines(api_client, other_budget, uuid.uuid4())
    assert got.status_code in (403, 404), got.text


async def test_one_split_endpoint_is_unchanged(api_client, db_session):
    budget, account = await _budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    services = make_services(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", TXN_DATE)
    parent = await services.transactions.convert_to_split(
        budget.id,
        txn.id,
        [
            SplitSpec(amount=Decimal("-7.00"), category_id=cat.id),
            SplitSpec(amount=Decimal("-3.00")),
        ],
    )
    got = await api_client.get(
        f"/api/v1/transactions/{parent.id}/splits", params={"budget_id": str(budget.id)}
    )
    assert got.status_code == 200, got.text
    lines = got.json()
    assert sorted(line["amount"] for line in lines) == [-7.0, -3.0]
    assert all(isinstance(line["needs_category"], bool) for line in lines)
    assert any(line["category_id"] == str(cat.id) for line in lines)

    plain = await create_transaction(db_session, budget, account, "-1.00", TXN_DATE)
    none = await api_client.get(
        f"/api/v1/transactions/{plain.id}/splits", params={"budget_id": str(budget.id)}
    )
    assert none.status_code == 200 and none.json() == []
