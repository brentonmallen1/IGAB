import { Layers, Pencil, Plus, Trash2, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useBudgetViews, useDeleteBudgetView } from '../../../api/budgetViews'
import { apiErrorMessage } from '../../../api/client'
import { useUIStore } from '../../../stores/uiStore'
import { confirmAsync } from '../../../stores/confirmStore'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import './ManageViewsModal.css'

interface Props {
  budgetId: string
  onClose: () => void
}

export function ManageViewsModal({ budgetId, onClose }: Props) {
  const { data: views } = useBudgetViews(budgetId)
  const deleteView = useDeleteBudgetView(budgetId)
  const activeViewId = useUIStore((s) => s.activeViewId)
  const setActiveView = useUIStore((s) => s.setActiveView)
  const openModal = useUIStore((s) => s.openModal)
  const trapRef = useFocusTrap<HTMLDivElement>(onClose)

  // openModal replaces the single modal slot, which closes this modal by
  // itself. Do NOT follow it with onClose(): that is closeModal(), and it
  // nulls the slot openModal just filled — the editor never rendered.
  function handleEdit(id: string) {
    openModal('view', id)
  }

  function handleNew() {
    openModal('view')
  }

  async function handleDelete(id: string, name: string) {
    const ok = await confirmAsync({
      title: `Delete the view “${name}”?`,
      message: 'Your budget’s own groups and categories are not affected.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    try {
      await deleteView.mutateAsync(id)
      // Deleting the view you are looking at drops you back to the budget's own
      // groups rather than leaving the page pointing at nothing.
      if (activeViewId === id) setActiveView(null)
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not delete this view'))
    }
  }

  return (
    <div
      className="manage-views-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={trapRef}
        tabIndex={-1}
        className="manage-views-modal"
        role="dialog"
        aria-modal
        aria-label="Manage views"
      >
        <div className="manage-views-modal__header">
          <span className="manage-views-modal__title">Manage Views</span>
          <button
            type="button"
            className="manage-views-modal__close"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="manage-views-modal__body">
          <p className="manage-views-modal__hint">
            A view arranges the same categories under groups you define — the same
            budget read a different way. Your own category groups are never changed,
            so you can switch back at any time.
          </p>

          <div className="manage-views-modal__section-header">
            <span>Saved Views</span>
            <button type="button" className="manage-views-modal__add-btn" onClick={handleNew}>
              <Plus size={13} />
              New View
            </button>
          </div>

          {!views || views.length === 0 ? (
            <p className="manage-views-modal__empty">
              No views yet. Create one to group these categories another way — by
              need and want, for instance — without touching your budget.
            </p>
          ) : (
            <div className="manage-views-modal__list">
              {views.map((v) => (
                <div key={v.id} className="manage-views-modal__row">
                  <span className="manage-views-modal__view-name">
                    {v.name}
                    {activeViewId === v.id && (
                      <span className="manage-views-modal__active">
                        <Layers size={11} /> in use
                      </span>
                    )}
                  </span>
                  <span className="manage-views-modal__meta">
                    {v.groups.length} {v.groups.length === 1 ? 'group' : 'groups'}
                  </span>
                  <div className="manage-views-modal__row-actions">
                    <button
                      type="button"
                      className="manage-views-modal__icon-btn"
                      onClick={() => handleEdit(v.id)}
                      aria-label={`Edit view ${v.name}`}
                      title="Edit view"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      type="button"
                      className="manage-views-modal__icon-btn manage-views-modal__icon-btn--danger"
                      onClick={() => handleDelete(v.id, v.name)}
                      disabled={deleteView.isPending}
                      aria-label={`Delete view ${v.name}`}
                      title="Delete view"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
