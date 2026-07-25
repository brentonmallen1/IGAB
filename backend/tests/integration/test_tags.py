"""Tag system integration tests."""

import pytest

from .factories import (
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_tag,
    create_user,
)

from igab.repositories.tag_repo import TagRepository, seed_system_tags


@pytest.mark.asyncio
async def test_create_and_list_tags(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    repo = TagRepository(db_session)
    tag = await repo.create(budget_id=budget.id, name="Travel", color_slot="blue")

    tags = await repo.list_for_budget(budget.id)
    assert len(tags) == 1
    assert tags[0].id == tag.id
    assert tags[0].name == "Travel"
    assert tags[0].color_slot == "blue"


@pytest.mark.asyncio
async def test_seed_system_tags(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    repo = TagRepository(db_session)
    await seed_system_tags(db_session, budget.id)

    tags = await repo.list_for_budget(budget.id)
    system_keys = {t.system_key for t in tags if t.system_key}
    assert system_keys == {"subscription", "savings", "long_term_expense"}


@pytest.mark.asyncio
async def test_seed_system_tags_idempotent(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    repo = TagRepository(db_session)
    await seed_system_tags(db_session, budget.id)
    await seed_system_tags(db_session, budget.id)  # Run twice

    tags = await repo.list_for_budget(budget.id)
    system_keys = [t.system_key for t in tags if t.system_key]
    assert len(system_keys) == 3  # Should still be 3, not 6


@pytest.mark.asyncio
async def test_set_category_tags_replace_set(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group)

    tag1 = await create_tag(db_session, budget, "Tag1")
    tag2 = await create_tag(db_session, budget, "Tag2")
    tag3 = await create_tag(db_session, budget, "Tag3")

    repo = TagRepository(db_session)

    # Set initial tags
    await repo.set_category_tags(category.id, [tag1.id, tag2.id])
    tags_map = await repo.get_tags_for_categories([category.id])
    assert len(tags_map[category.id]) == 2

    # Replace with different set
    await repo.set_category_tags(category.id, [tag2.id, tag3.id])
    tags_map = await repo.get_tags_for_categories([category.id])
    tag_ids = {t.id for t in tags_map[category.id]}
    assert tag_ids == {tag2.id, tag3.id}

    # Clear all
    await repo.set_category_tags(category.id, [])
    tags_map = await repo.get_tags_for_categories([category.id])
    assert len(tags_map[category.id]) == 0


@pytest.mark.asyncio
async def test_set_payee_tags_replace_set(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    payee = await create_payee(db_session, budget)

    tag1 = await create_tag(db_session, budget, "Tag1")
    tag2 = await create_tag(db_session, budget, "Tag2")

    repo = TagRepository(db_session)

    await repo.set_payee_tags(payee.id, [tag1.id])
    tags_map = await repo.get_tags_for_payees([payee.id])
    assert len(tags_map[payee.id]) == 1

    await repo.set_payee_tags(payee.id, [tag1.id, tag2.id])
    tags_map = await repo.get_tags_for_payees([payee.id])
    assert len(tags_map[payee.id]) == 2


@pytest.mark.asyncio
async def test_add_and_remove_payee_tag(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    payee = await create_payee(db_session, budget)
    tag = await create_tag(db_session, budget, "Subscription", system_key="subscription")

    repo = TagRepository(db_session)

    # Add tag
    await repo.add_payee_tag(payee.id, tag.id)
    tags_map = await repo.get_tags_for_payees([payee.id])
    assert len(tags_map[payee.id]) == 1

    # Add same tag again (no-op, no error)
    await repo.add_payee_tag(payee.id, tag.id)
    tags_map = await repo.get_tags_for_payees([payee.id])
    assert len(tags_map[payee.id]) == 1

    # Remove tag
    await repo.remove_payee_tag(payee.id, tag.id)
    tags_map = await repo.get_tags_for_payees([payee.id])
    assert len(tags_map[payee.id]) == 0


@pytest.mark.asyncio
async def test_get_category_system_keys(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget)
    category1 = await create_category(db_session, budget, group, "Savings Fund")
    category2 = await create_category(db_session, budget, group, "Groceries")

    savings_tag = await create_tag(db_session, budget, "Savings", system_key="savings")
    user_tag = await create_tag(db_session, budget, "Important")

    repo = TagRepository(db_session)

    # Tag category1 with both system and user tag
    await repo.set_category_tags(category1.id, [savings_tag.id, user_tag.id])
    # Tag category2 with only user tag
    await repo.set_category_tags(category2.id, [user_tag.id])

    system_keys = await repo.get_category_system_keys(budget.id)

    # Only category1 should have a system key entry
    assert category1.id in system_keys
    assert "savings" in system_keys[category1.id]
    assert category2.id not in system_keys  # No system keys


@pytest.mark.asyncio
async def test_list_for_budget_with_counts(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group)
    payee1 = await create_payee(db_session, budget, "Payee1")
    payee2 = await create_payee(db_session, budget, "Payee2")

    tag = await create_tag(db_session, budget, "TestTag")

    repo = TagRepository(db_session)
    await repo.set_category_tags(category.id, [tag.id])
    await repo.set_payee_tags(payee1.id, [tag.id])
    await repo.set_payee_tags(payee2.id, [tag.id])

    tags_with_counts = await repo.list_for_budget_with_counts(budget.id)
    assert len(tags_with_counts) == 1
    t, cat_count, payee_count = tags_with_counts[0]
    assert t.id == tag.id
    assert cat_count == 1
    assert payee_count == 2


@pytest.mark.asyncio
async def test_delete_tag_clears_associations(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group)
    payee = await create_payee(db_session, budget)

    tag = await create_tag(db_session, budget, "ToDelete")

    repo = TagRepository(db_session)
    await repo.set_category_tags(category.id, [tag.id])
    await repo.set_payee_tags(payee.id, [tag.id])

    await repo.delete_with_associations(tag.id)

    # Tag should be soft-deleted
    deleted_tag = await repo.get(tag.id)
    assert deleted_tag is None  # get respects is_deleted

    # Associations should be cleared
    cat_tags = await repo.get_tags_for_categories([category.id])
    payee_tags = await repo.get_tags_for_payees([payee.id])
    assert len(cat_tags[category.id]) == 0
    assert len(payee_tags[payee.id]) == 0


@pytest.mark.asyncio
async def test_get_by_name_case_insensitive(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    repo = TagRepository(db_session)
    tag = await repo.create(budget_id=budget.id, name="Travel")

    found = await repo.get_by_name(budget.id, "travel")
    assert found is not None
    assert found.id == tag.id

    found_upper = await repo.get_by_name(budget.id, "TRAVEL")
    assert found_upper is not None
    assert found_upper.id == tag.id
