"""Tag system integration tests."""

import pytest

from igab.repositories.tag_repo import SYSTEM_TAGS, TagRepository, seed_system_tags

from .factories import (
    create_budget,
    create_category,
    create_category_group,
    create_tag,
    create_user,
)


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
    # Derived, not hardcoded: adding a system tag should not need a test edit.
    assert system_keys == {key for key, _, _ in SYSTEM_TAGS}


@pytest.mark.asyncio
async def test_seed_system_tags_idempotent(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    repo = TagRepository(db_session)
    await seed_system_tags(db_session, budget.id)
    await seed_system_tags(db_session, budget.id)  # Run twice

    tags = await repo.list_for_budget(budget.id)
    system_keys = [t.system_key for t in tags if t.system_key]
    assert len(system_keys) == len(SYSTEM_TAGS), "seeding twice must not duplicate"


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

    tag = await create_tag(db_session, budget, "TestTag")

    repo = TagRepository(db_session)
    await repo.set_category_tags(category.id, [tag.id])

    # No payee count: tags on payees are retired, so it would be a zero printed
    # beside every tag in the Tags panel forever.
    tags_with_counts = await repo.list_for_budget_with_counts(budget.id)
    assert len(tags_with_counts) == 1
    t, cat_count = tags_with_counts[0]
    assert t.id == tag.id
    assert cat_count == 1


@pytest.mark.asyncio
async def test_delete_tag_clears_associations(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group)

    tag = await create_tag(db_session, budget, "ToDelete")

    repo = TagRepository(db_session)
    await repo.set_category_tags(category.id, [tag.id])

    await repo.delete_with_associations(tag.id)

    # Tag should be soft-deleted
    deleted_tag = await repo.get(tag.id)
    assert deleted_tag is None  # get respects is_deleted

    # Associations should be cleared
    cat_tags = await repo.get_tags_for_categories([category.id])
    assert len(cat_tags[category.id]) == 0


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
