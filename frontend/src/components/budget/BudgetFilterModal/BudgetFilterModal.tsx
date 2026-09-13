import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { apiErrorMessage } from '../../../api/client'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useCreateTag, useTags } from '../../../api/tags'
import { TagPicker, type TagOption } from '../../common/TagPicker'
import { TagChip } from '../../common/TagChip'
import { renderableCategories, renderableGroups } from '../budgetGroups'
import {
  useBudgetFilters,
  useCreateBudgetFilter,
  useDeleteBudgetFilter,
  useUpdateBudgetFilter,
} from '../../../api/budgetFilters'
import { useUIStore } from '../../../stores/uiStore'
import { Dialog } from '../../common/Dialog/Dialog'
import './BudgetFilterModal.css'

/** The form scrolls; its submit button is in the pinned footer, joined by id. */
const FORM_ID = 'filter-modal-form'

interface Props {
  budgetId: string
  filterId: string | null
  onClose: () => void
}

export function BudgetFilterModal({ budgetId, filterId, onClose }: Props) {
  const { data: filters } = useBudgetFilters(budgetId)
  const { data: allGroups = [] } = useCategoryGroups(budgetId, true)
  const { data: allCategories = [] } = useCategories(budgetId, true)
  const { data: tags = [] } = useTags(budgetId)
  const createTag = useCreateTag(budgetId)
  // The same rule the grid draws by: a system (Income) group has no envelope
  // rows, so offering its category here was a checkbox that changed nothing.
  const groups = useMemo(() => renderableGroups(allGroups), [allGroups])
  // Hidden categories are offered here on purpose — a filter may name one.
  // A card's set-aside envelope is different: it is never a grid row, so
  // there is nothing to filter it into or out of. The same rule the grid
  // draws by, from the same place, or "Credit Card Payments" appears here
  // as a group of checkboxes that change nothing.
  const categories = useMemo(() => renderableCategories(allCategories), [allCategories])
  const createFilter = useCreateBudgetFilter(budgetId)
  const updateFilter = useUpdateBudgetFilter(budgetId)
  const deleteFilter = useDeleteBudgetFilter(budgetId)
  const setActiveFilter = useUIStore((s) => s.setActiveFilter)
  const activeFilterId = useUIStore((s) => s.activeFilterId)

  const existingFilter = filters?.find((v) => v.id === filterId) ?? null
  const isEdit = !!existingFilter

  const [name, setName] = useState(existingFilter?.name ?? '')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(existingFilter?.category_ids ?? [])
  )
  const [tagIds, setTagIds] = useState<string[]>(existingFilter?.tag_ids ?? [])
  const tagOptions: TagOption[] = useMemo(
    () => tags.map((t) => ({ id: t.id, name: t.name, color_slot: t.color_slot })),
    [tags]
  )
  const tagById = useMemo(() => new Map(tags.map((t) => [t.id, t])), [tags])
  const nameRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const tagsLabelId = useId()
  const categoriesLabelId = useId()

  useEffect(() => {
    nameRef.current?.focus()
  }, [])

  function toggleCategory(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleGroup(groupId: string) {
    const groupCatIds = categories.filter((c) => c.category_group_id === groupId).map((c) => c.id)
    const allSelected = groupCatIds.every((id) => selectedIds.has(id))
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (allSelected) groupCatIds.forEach((id) => next.delete(id))
      else groupCatIds.forEach((id) => next.add(id))
      return next
    })
  }

  function getGroupState(groupId: string): 'all' | 'some' | 'none' {
    const groupCatIds = categories.filter((c) => c.category_group_id === groupId).map((c) => c.id)
    if (groupCatIds.length === 0) return 'none'
    const selected = groupCatIds.filter((id) => selectedIds.has(id)).length
    if (selected === groupCatIds.length) return 'all'
    if (selected > 0) return 'some'
    return 'none'
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return setError('Give this filter a name')
    setError(null)
    const categoryIds = Array.from(selectedIds)
    try {
      if (isEdit && existingFilter) {
        await updateFilter.mutateAsync({
          id: existingFilter.id,
          name: trimmed,
          category_ids: categoryIds,
          tag_ids: tagIds,
        })
      } else {
        const created = await createFilter.mutateAsync({
          name: trimmed,
          category_ids: categoryIds,
          tag_ids: tagIds,
        })
        setActiveFilter(created.id)
      }
    } catch (err: unknown) {
      return setError(apiErrorMessage(err, 'Could not save this filter'))
    }
    onClose()
  }

  async function handleDelete() {
    if (!existingFilter) return
    try {
      await deleteFilter.mutateAsync(existingFilter.id)
    } catch (err: unknown) {
      return setError(apiErrorMessage(err, 'Could not delete this filter'))
    }
    if (activeFilterId === existingFilter.id) setActiveFilter(null)
    onClose()
  }

  const isPending = createFilter.isPending || updateFilter.isPending || deleteFilter.isPending

  return (
    <Dialog
      title={isEdit ? 'Edit Filter' : 'New Filter'}
      onClose={onClose}
      historyKey="budget-filter"
      className="filter-modal"
      footer={
        <div className="dialog-actions">
          {isEdit && (
            <button
              type="button"
              className="dialog-btn dialog-btn--danger"
              onClick={handleDelete}
              disabled={isPending}
            >
              Delete
            </button>
          )}
          {error && (
            <span className="dialog-form__error" role="alert">
              {error}
            </span>
          )}
          <div className="dialog-actions__end">
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={onClose}
              disabled={isPending}
            >
              Cancel
            </button>
            {/* The footer is pinned outside the form; `form=` joins them. */}
            <button
              type="submit"
              form={FORM_ID}
              className="dialog-btn dialog-btn--primary"
              disabled={isPending}
            >
              {isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      }
    >
      <form id={FORM_ID} className="dialog-form" onSubmit={handleSubmit}>
        <p className="dialog-form__hint">
          Choose a set of categories to include in this custom filter.
        </p>

        <label className="dialog-form__field">
          <span>Filter name</span>
          <input
            ref={nameRef}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Keep 'em short & sweet!"
          />
        </label>

        <div className="dialog-form__field" role="group" aria-labelledby={tagsLabelId}>
          <span id={tagsLabelId}>Include every category tagged…</span>
          <div className="filter-modal__tags">
            {tagIds.map((id) => {
              const tag = tagById.get(id)
              return tag ? (
                <TagChip
                  key={id}
                  name={tag.name}
                  colorSlot={tag.color_slot}
                  onRemove={() => setTagIds((prev) => prev.filter((t) => t !== id))}
                />
              ) : null
            })}
            <TagPicker
              selectedTagIds={tagIds}
              tags={tagOptions}
              onChange={setTagIds}
              allowCreate
              onCreateTag={async (name) => {
                const tag = await createTag.mutateAsync({ name })
                return { id: tag.id, name: tag.name, color_slot: tag.color_slot }
              }}
              triggerLabel="+ Tag"
            />
          </div>
          <p className="dialog-form__hint">
            A tag follows its categories: tag one later and it joins this filter; untag it and it
            leaves.
          </p>
        </div>

        <div className="dialog-form__field" role="group" aria-labelledby={categoriesLabelId}>
          <span id={categoriesLabelId}>…and these categories</span>
          <div className="filter-modal__category-list">
            {groups.map((group) => {
              const groupCats = categories.filter((c) => c.category_group_id === group.id)
              if (groupCats.length === 0) return null
              const state = getGroupState(group.id)
              return (
                <div key={group.id} className="filter-modal__group">
                  <label className="filter-modal__group-header">
                    <IndeterminateCheckbox
                      checked={state === 'all'}
                      indeterminate={state === 'some'}
                      onChange={() => toggleGroup(group.id)}
                    />
                    <span className="filter-modal__group-name">{group.name}</span>
                  </label>
                  {groupCats.map((cat) => (
                    <label key={cat.id} className="filter-modal__cat-row">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(cat.id)}
                        onChange={() => toggleCategory(cat.id)}
                      />
                      <span>{cat.name}</span>
                    </label>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      </form>
    </Dialog>
  )
}

function IndeterminateCheckbox({
  checked,
  indeterminate,
  onChange,
}: {
  checked: boolean
  indeterminate: boolean
  onChange: () => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate
  }, [indeterminate])
  return <input type="checkbox" ref={ref} checked={checked} onChange={onChange} />
}
