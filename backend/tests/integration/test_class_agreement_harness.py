"""Proving the differential harness can actually fail.

A test that compares an implementation with itself passes trivially and would
keep passing if the comparison were broken. So each check here feeds the
harness a deliberately wrong implementation and requires it to notice — the
three ways a rewrite of `ACTIVITY_CLASS` could go wrong:

  * a rule stops firing, so rows fall through to a different class;
  * the joins fan out, so every total multiplies while looking plausible;
  * the right class arrives via the wrong rule, so the explanation shown to
    the user is a lie even though the number is correct.

Run against the full-tier sample budget rather than a hand-built fixture: 16
accounts, 30 months, a tracked brokerage, a managed mortgage, transfers and
splits. Hand-built data only contains the cases you remembered.
"""

import pytest
from sqlalchemy import case, literal, select
from sqlalchemy.orm import aliased

from igab.db.models import Account, Transaction
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    ACTIVITY_CLASS_SUBQUERY,
    ACTIVITY_REASON,
    ACTIVITY_REASON_SUBQUERY,
    RULES,
    ActivityClass,
    ActivityReason,
    apply_class_joins,
)
from igab.repositories.tag_repo import TagRepository
from igab.repositories.txn_filters import LEAF, NOT_DELETED, POSTED

from .class_agreement import ClassImpl, assert_class_agreement
from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)
from .invariants import assert_activity_class_partition

# The full-tier generator lives with its own tests; this borrows it rather
# than growing a second copy that could drift from the shipped sample data.
from .test_sample_budget_full import ANCHOR, generate_full

#: The previous implementation, kept only for this comparison.
ORACLE = ClassImpl(
    name="subquery",
    cls=ACTIVITY_CLASS_SUBQUERY,
    reason=ACTIVITY_REASON_SUBQUERY,
    joins=None,
)
#: What actually ships. `joins` defaults to CLASS_JOINS, which is the point:
#: this is exercised the way the reports build their queries.
SHIPPED = ClassImpl(name="joined", cls=ACTIVITY_CLASS, reason=ACTIVITY_REASON)


async def _cover_the_rules_the_sample_data_misses(db_session, budget) -> None:
    """Two of the eight rules never fire over the sample budget.

    Found by the drop-a-rule check below, which is the whole reason it is
    parameterised over every rule rather than testing one: realistic data is
    necessary for a differential test and not sufficient, because it only
    contains the situations the sample author had a reason to model.

    The gaps, both plausible in a real budget and neither present in ours:

      * a category tagged **debt principal** that is not also a transfer to a
        tracked loan — someone paying a debt that IGAB does not track;
      * an **uncategorized transfer to a tracked asset** — the YNAB-import
        shape the savings rule exists for, where the destination decides the
        class because the user never categorised the leg.
    """
    tags = TagRepository(db_session)
    group = await create_category_group(db_session, budget, "Coverage")
    checking = await create_account(db_session, budget, "Coverage Checking", on_budget=True)

    debt_tag = await tags.get_system_tag(budget.id, "debt_principal")
    assert debt_tag is not None, "system tags are seeded by generate_full"
    tagged_debt = await create_category(db_session, budget, group, "Loan From A Friend")
    await tags.set_category_tags(tagged_debt.id, [debt_tag.id])
    shop = await create_payee(db_session, budget, "Repayment")
    await create_transaction(
        db_session, budget, checking, "-120.00", ANCHOR, category=tagged_debt, payee=shop
    )

    brokerage = await create_account(
        db_session, budget, "Coverage Brokerage", account_type="investment", on_budget=False
    )
    to_brokerage = await create_payee(
        db_session, budget, "Transfer : Coverage Brokerage", transfer_account_id=brokerage.id
    )
    await create_transaction(db_session, budget, checking, "-300.00", ANCHOR, payee=to_brokerage)


async def _full_budget(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await generate_full(db_session, budget)
    await _cover_the_rules_the_sample_data_misses(db_session, budget)
    return budget


def _case_without(index: int) -> ClassImpl:
    """The real rules minus one — a rule that quietly stopped matching."""
    kept = [rule for i, rule in enumerate(RULES) if i != index]
    return ClassImpl(
        name=f"missing-rule-{index}",
        cls=case(
            *[(cond, literal(cls.value)) for cond, cls, _ in kept],
            else_=literal(ActivityClass.SPENDING.value),
        ),
        reason=case(
            *[(cond, literal(reason.value)) for cond, _, reason in kept],
            else_=literal(ActivityReason.DEFAULT_SPENDING.value),
        ),
    )


class TestTheFixtureExercisesEveryRule:
    """A differential test is only as good as the rows it runs over. If a rule
    never fires here, a rewrite could break it and every check below would
    still pass."""

    async def test_every_rule_fires_at_least_once(self, db_session):
        budget = await _full_budget(db_session)
        # Transaction.id is not wanted; the joins chain from `transactions`, so
        # the statement has to be anchored on it.
        q = apply_class_joins(
            select(Transaction.id, ACTIVITY_REASON).where(
                Transaction.budget_id == budget.id, NOT_DELETED, POSTED, LEAF
            )
        )
        reasons = {row[1] for row in (await db_session.execute(q)).all()}
        missing = {r.value for r in ActivityReason} - reasons
        assert not missing, (
            f"no row in the fixture reaches: {sorted(missing)} — a rewrite could "
            "break those rules with every differential check still green"
        )


class TestTheHarnessCatchesWhatItIsFor:
    async def test_the_reference_agrees_with_itself_over_real_data(self, db_session):
        """The baseline — and a check that the fixture is big enough to mean
        something. A harness run over six rows proves very little."""
        budget = await _full_budget(db_session)
        compared = await assert_class_agreement(db_session, budget.id, SHIPPED, SHIPPED)
        assert compared > 500, f"only {compared} rows compared — the fixture has shrunk"

    @pytest.mark.parametrize("dropped", range(len(RULES)))
    async def test_dropping_any_single_rule_is_caught(self, db_session, dropped):
        """Every rule must be load-bearing over this data. A rule that can be
        removed without the harness noticing is a rule this fixture does not
        exercise — which would be worth knowing before trusting the harness."""
        budget = await _full_budget(db_session)
        with pytest.raises(AssertionError, match="disagree about"):
            await assert_class_agreement(db_session, budget.id, SHIPPED, _case_without(dropped))

    async def test_a_fanning_out_join_is_caught(self, db_session):
        """The failure mode that does not look like one: a join matching more
        than once per transaction multiplies every total downstream."""
        budget = await _full_budget(db_session)
        other = aliased(Account)
        fanning = ClassImpl(
            name="fanned",
            cls=ACTIVITY_CLASS,
            reason=ACTIVITY_REASON,
            joins=lambda stmt: apply_class_joins(stmt).join(
                other, other.budget_id == Transaction.budget_id
            ),
        )
        with pytest.raises(AssertionError, match="the joins fan out"):
            await assert_class_agreement(db_session, budget.id, SHIPPED, fanning)

    async def test_the_right_class_for_the_wrong_reason_is_caught(self, db_session):
        """Class and reason are compared together on purpose. A row can be
        correctly called savings by a rule that should not have fired, and the
        user is then shown an explanation that does not match their data."""
        budget = await _full_budget(db_session)
        wrong_reason = ClassImpl(
            name="reason-blind",
            cls=ACTIVITY_CLASS,
            reason=literal(ActivityReason.DEFAULT_SPENDING.value),
        )
        with pytest.raises(AssertionError, match="disagree about"):
            await assert_class_agreement(db_session, budget.id, SHIPPED, wrong_reason)

    async def test_the_partition_invariant_follows_the_seam(self, db_session):
        """The other half of the safety net, and the reason CLASS_JOINS exists.

        `assert_activity_class_partition` runs at 48 call sites. If the
        expression moves to joins and the invariant keeps building its query
        the old way, all 48 keep passing while every report fans out. Point
        the seam at a join that duplicates and the invariant must fail — if it
        does not, it is checking a code path nothing uses.
        """
        import igab.domain.activity_class as ac

        budget = await _full_budget(db_session)
        await assert_activity_class_partition(db_session, budget.id)  # baseline

        other = aliased(Account)

        # The real joins plus a duplicating one: the shape of a rewrite that
        # is correct about columns and wrong about cardinality.
        def monkey(stmt):
            return apply_class_joins(stmt).join(other, other.budget_id == Transaction.budget_id)

        original = ac.CLASS_JOINS
        ac.CLASS_JOINS = monkey
        try:
            with pytest.raises(AssertionError, match="partition is not total"):
                await assert_activity_class_partition(db_session, budget.id)
        finally:
            ac.CLASS_JOINS = original

        await assert_activity_class_partition(db_session, budget.id)  # and back

    async def test_forgetting_the_joins_entirely_is_caught(self, db_session):
        """The mistake a future consumer will actually make. Using the shipped
        expression without CLASS_JOINS leaves its aliased tables unjoined in
        the FROM — a cartesian product, and every total multiplied. SQLAlchemy
        only warns; pyproject promotes that warning to an error so it lands as
        a failure wherever it happens rather than as a number in a chart."""
        import sqlalchemy.exc

        budget = await _full_budget(db_session)
        unjoined = ClassImpl(
            name="no-joins", cls=ACTIVITY_CLASS, reason=ACTIVITY_REASON, joins=None
        )
        with pytest.raises((AssertionError, sqlalchemy.exc.SAWarning)):
            await assert_class_agreement(db_session, budget.id, SHIPPED, unjoined)

    async def test_an_empty_budget_is_refused_rather_than_passing(self, db_session):
        """The worst outcome for a differential test is a green run over no
        rows. Point it at an empty budget and it must say so."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        with pytest.raises(AssertionError, match="no posted leaf rows"):
            await assert_class_agreement(db_session, budget.id, SHIPPED, SHIPPED)


class TestTheShippedImplementationMatchesTheOracle:
    """The claim the rewrite has to earn.

    The rules themselves are shared — `_rules()` is written once and given
    either set of inputs — so what is under test here is narrower and more
    honest than "two rule sets agree": it is whether reading a column through
    a LEFT JOIN says the same thing as reading it through a correlated
    subquery, including where NULL is involved.
    """

    async def test_they_agree_about_every_row_of_a_real_budget(self, db_session):
        budget = await _full_budget(db_session)
        compared = await assert_class_agreement(db_session, budget.id, ORACLE, SHIPPED)
        assert compared > 500

    async def test_the_joined_version_stays_one_row_per_transaction(self, db_session):
        """Stated separately from agreement because it is the failure that does
        not announce itself. `assert_class_agreement` already refuses to return
        without checking, but a fan-out is worth its own named test."""
        budget = await _full_budget(db_session)
        rows = (
            await db_session.execute(
                apply_class_joins(
                    select(Transaction.id).where(
                        Transaction.budget_id == budget.id, NOT_DELETED, POSTED, LEAF
                    )
                )
            )
        ).all()
        assert len(rows) == len({r.id for r in rows})

    async def test_they_agree_on_the_awkward_shapes_too(self, db_session):
        """The sample budget is realistic but tidy. These are the rows that
        historically broke classification: an orphaned transfer leg whose
        partner is gone, a soft-deleted partner, and a leg pointing at an
        account that no longer exists.
        """
        budget = await _full_budget(db_session)
        checking = await create_account(db_session, budget, "Awkward", on_budget=True)
        gone = await create_account(db_session, budget, "Closed Brokerage", on_budget=False)

        # A transfer payee whose account was deleted outright.
        orphan_payee = await create_payee(
            db_session, budget, "Transfer : Closed Brokerage", transfer_account_id=gone.id
        )
        await create_transaction(db_session, budget, checking, "-40.00", ANCHOR, payee=orphan_payee)

        # A leg with a transfer_id pointing at a soft-deleted partner.
        partner = await create_transaction(
            db_session, budget, gone, "40.00", ANCHOR, is_deleted=True
        )
        await create_transaction(
            db_session, budget, checking, "-40.00", ANCHOR, transfer_id=partner.id
        )

        # A payee with no transfer account at all, on an uncategorised row.
        plain = await create_payee(db_session, budget, "Corner Shop")
        await create_transaction(db_session, budget, checking, "-15.00", ANCHOR, payee=plain)

        await assert_class_agreement(db_session, budget.id, ORACLE, SHIPPED)
