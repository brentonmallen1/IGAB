import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import {
  useBudgetFilters,
  useCreateBudgetFilter,
  useDeleteBudgetFilter,
  useUpdateBudgetFilter,
} from '../../../api/budgetFilters'
import { useUIStore } from '../../../stores/uiStore'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import './BudgetFilterModal.css'

interface Props {
  budgetId: string
  filterId: string | null
  onClose: () => void
}

export function BudgetFilterModal({ budgetId, filterId, onClose }: Props) {
  const { data: filters } = useBudgetFilters(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId, true)
  const { data: categories = [] } = useCategories(budgetId, true)
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
  const nameRef = useRef<HTMLInputElement>(null)
  const trapRef = useFocusTrap<HTMLFormElement>(onClose)

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
    if (!trimmed) return
    const categoryIds = Array.from(selectedIds)
    if (isEdit && existingFilter) {
      await updateFilter.mutateAsync({ id: existingFilter.id, name: trimmed, category_ids: categoryIds })
    } else {
      const created = await createFilter.mutateAsync({ name: trimmed, category_ids: categoryIds })
      setActiveFilter(created.id)
    }
    onClose()
  }

  async function handleDelete() {
    if (!existingFilter) return
    await deleteFilter.mutateAsync(existingFilter.id)
    if (activeFilterId === existingFilter.id) setActiveFilter(null)
    onClose()
  }

  const isPending = createFilter.isPending || updateFilter.isPending || deleteFilter.isPending

  return (
    <div
      className="filter-modal-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <form ref={trapRef} tabIndex={-1} className="filter-modal" onSubmit={handleSubmit} role="dialog" aria-modal aria-labelledby="filter-modal-title">
        <div className="filter-modal__header">
          <span id="filter-modal-title" className="filter-modal__title">{isEdit ? 'Edit Filter' : 'New Filter'}</span>
          <button type="button" className="filter-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="filter-modal__body">
          <p className="filter-modal__subtitle">
            Choose a set of categories to include in this custom filter.
          </p>

          <div className="filter-modal__field">
            <label className="filter-modal__label" htmlFor="filter-name">
              Filter Name
            </label>
            <input
              id="filter-name"
              ref={nameRef}
              className="filter-modal__input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Keep 'em short & sweet!"
              required
            />
          </div>

          <div className="filter-modal__field">
            <label className="filter-modal__label">Select the categories below to include.</label>
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
        </div>

        <div className="filter-modal__footer">
          {isEdit && (
            <button
              type="button"
              className="filter-modal__btn filter-modal__btn--danger"
              onClick={handleDelete}
              disabled={isPending}
            >
              Delete
            </button>
          )}
          <div className="filter-modal__footer-right">
            <button
              type="button"
              className="filter-modal__btn filter-modal__btn--secondary"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="filter-modal__btn filter-modal__btn--primary"
              disabled={isPending}
            >
              Save
            </button>
          </div>
        </div>
      </form>
    </div>
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
