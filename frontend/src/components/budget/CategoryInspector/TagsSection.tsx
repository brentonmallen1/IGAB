import { useTags, useSetCategoryTags, useCreateTag } from '../../../api/tags'
import { TagChip } from '../../common/TagChip'
import { TagPicker, type TagOption } from '../../common/TagPicker'
import type { Category } from '../../../types'
import { SystemTagsHelp } from '../../settings/TagsPanel/SystemTagsHelp'

interface TagsSectionProps {
  category: Category
  budgetId: string
}

export function TagsSection({ category, budgetId }: TagsSectionProps) {
  const { data: allTags } = useTags(budgetId)
  const setTags = useSetCategoryTags(budgetId)
  const createTag = useCreateTag(budgetId)

  const selectedTagIds = category.tags?.map((t) => t.id) ?? []

  const tagOptions: TagOption[] =
    allTags?.map((t) => ({
      id: t.id,
      name: t.name,
      color_slot: t.color_slot,
    })) ?? []

  function handleChange(tagIds: string[]) {
    setTags.mutate({ categoryId: category.id, tagIds })
  }

  async function handleCreate(name: string): Promise<TagOption> {
    const tag = await createTag.mutateAsync({ name })
    return { id: tag.id, name: tag.name, color_slot: tag.color_slot }
  }

  return (
    <div className="inspector-section">
      <div className="inspector-section__header">
        <span className="inspector-section__title">Tags</span>
        {/* The same popover the Tags settings panel shows: what each system
            tag does to the numbers, and which of them apply here. */}
        <SystemTagsHelp />
      </div>
      <div className="inspector-tags">
        {category.tags && category.tags.length > 0 ? (
          <div className="inspector-tags__list">
            {category.tags.map((tag) => (
              <TagChip
                key={tag.id}
                name={tag.name}
                colorSlot={tag.color_slot}
                onRemove={() => handleChange(selectedTagIds.filter((id) => id !== tag.id))}
              />
            ))}
          </div>
        ) : (
          <span className="inspector-tags__empty">No tags</span>
        )}
        <div className="inspector-section__actions">
          <TagPicker
            selectedTagIds={selectedTagIds}
            tags={tagOptions}
            onChange={handleChange}
            onCreateTag={handleCreate}
            allowCreate
            triggerLabel="+ Tag"
            ghost
          />
        </div>
      </div>
    </div>
  )
}
