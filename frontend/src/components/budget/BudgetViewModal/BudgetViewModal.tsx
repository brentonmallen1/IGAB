import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import {
  useBudgetViews,
  useCreateBudgetView,
  useDeleteBudgetView,
  useUpdateBudgetView,
} from '../../../api/budgetViews'
import { useUIStore } from '../../../stores/uiStore'
import './BudgetViewModal.css'

interface Props {
  budgetId: string
  viewId: string | null
  onClose: () => void
}

export function BudgetViewModal({ budgetId, viewId, onClose }: Props) {
  const { data: views } = useBudgetViews(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId, true)
  const { data: categories = [] } = useCategories(budgetId, true)
  const createView = useCreateBudgetView(budgetId)
  const updateView = useUpdateBudgetView(budgetId)
  const deleteView = useDeleteBudgetView(budgetId)
  const setActiveBudgetView = useUIStore((s) => s.setActiveBudgetView)
  const activeBudgetViewId = useUIStore((s) => s.activeBudgetViewId)

  const existingView = views?.find((v) => v.id === viewId) ?? null
  const isEdit = !!existingView

  const [name, setName] = useState(existingView?.name ?? '')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(existingView?.category_ids ?? [])
  )
  const nameRef = useRef<HTMLInputElement>(null)

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
    if (isEdit && existingView) {
      await updateView.mutateAsync({ id: existingView.id, name: trimmed, category_ids: categoryIds })
    } else {
      const created = await createView.mutateAsync({ name: trimmed, category_ids: categoryIds })
      setActiveBudgetView(created.id)
    }
    onClose()
  }

  async function handleDelete() {
    if (!existingView) return
    await deleteView.mutateAsync(existingView.id)
    if (activeBudgetViewId === existingView.id) setActiveBudgetView(null)
    onClose()
  }

  const isPending = createView.isPending || updateView.isPending || deleteView.isPending

  return (
    <div
      className="view-modal-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <form className="view-modal" onSubmit={handleSubmit} role="dialog" aria-modal>
        <div className="view-modal__header">
          <span className="view-modal__title">{isEdit ? 'Edit View' : 'New Custom View'}</span>
          <button type="button" className="view-modal__close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="view-modal__body">
          <p className="view-modal__subtitle">
            Choose a set of categories to include in this custom view.
          </p>

          <div className="view-modal__field">
            <label className="view-modal__label" htmlFor="view-name">
              View Name
            </label>
            <input
              id="view-name"
              ref={nameRef}
              className="view-modal__input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Keep 'em short & sweet!"
              required
            />
          </div>

          <div className="view-modal__field">
            <label className="view-modal__label">Select the categories below to include.</label>
            <div className="view-modal__category-list">
              {groups.map((group) => {
                const groupCats = categories.filter((c) => c.category_group_id === group.id)
                if (groupCats.length === 0) return null
                const state = getGroupState(group.id)
                return (
                  <div key={group.id} className="view-modal__group">
                    <label className="view-modal__group-header">
                      <IndeterminateCheckbox
                        checked={state === 'all'}
                        indeterminate={state === 'some'}
                        onChange={() => toggleGroup(group.id)}
                      />
                      <span className="view-modal__group-name">{group.name}</span>
                    </label>
                    {groupCats.map((cat) => (
                      <label key={cat.id} className="view-modal__cat-row">
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

        <div className="view-modal__footer">
          {isEdit && (
            <button
              type="button"
              className="view-modal__btn view-modal__btn--danger"
              onClick={handleDelete}
              disabled={isPending}
            >
              Delete
            </button>
          )}
          <div className="view-modal__footer-right">
            <button
              type="button"
              className="view-modal__btn view-modal__btn--secondary"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="view-modal__btn view-modal__btn--primary"
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
