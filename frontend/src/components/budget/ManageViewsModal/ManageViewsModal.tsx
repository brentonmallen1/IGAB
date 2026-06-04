import { useState } from 'react'
import { X, GripVertical, Pencil, Trash2, Plus, Lock } from 'lucide-react'
import { useBudgetViews, useDeleteBudgetView } from '../../../api/budgetViews'
import { useUIStore, ALL_QUICK_FILTERS } from '../../../stores/uiStore'
import type { QuickFilter } from '../../../stores/uiStore'
import './ManageViewsModal.css'

interface Props {
  budgetId: string
  onClose: () => void
}

const QUICK_FILTER_LABELS: Record<QuickFilter, string> = {
  overspent: 'Overspent',
  underfunded: 'Underfunded',
  'money-available': 'Money Available',
  overfunded: 'Overfunded',
}

const QUICK_FILTER_VARIANTS: Record<QuickFilter, string> = {
  overspent: 'negative',
  underfunded: 'warning',
  'money-available': 'positive',
  overfunded: 'positive',
}

export function ManageViewsModal({ budgetId, onClose }: Props) {
  const { data: views } = useBudgetViews(budgetId)
  const deleteView = useDeleteBudgetView(budgetId)
  const openViewModal = useUIStore((s) => s.openViewModal)
  const quickFilterOrder = useUIStore((s) => s.quickFilterOrder)
  const reorderQuickFilters = useUIStore((s) => s.reorderQuickFilters)
  const activeBudgetViewId = useUIStore((s) => s.activeBudgetViewId)
  const setActiveBudgetView = useUIStore((s) => s.setActiveBudgetView)

  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)

  function handleDragStart(index: number) {
    setDragIndex(index)
  }

  function handleDragOver(e: React.DragEvent, index: number) {
    e.preventDefault()
    setDragOverIndex(index)
  }

  function handleDrop(e: React.DragEvent, dropIndex: number) {
    e.preventDefault()
    if (dragIndex === null || dragIndex === dropIndex) {
      setDragIndex(null)
      setDragOverIndex(null)
      return
    }
    const next = [...quickFilterOrder]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(dropIndex, 0, moved)
    reorderQuickFilters(next)
    setDragIndex(null)
    setDragOverIndex(null)
  }

  function handleDragEnd() {
    setDragIndex(null)
    setDragOverIndex(null)
  }

  async function handleDeleteView(id: string) {
    await deleteView.mutateAsync(id)
    if (activeBudgetViewId === id) setActiveBudgetView(null)
  }

  function handleEditView(id: string) {
    openViewModal(id)
    onClose()
  }

  function handleNewView() {
    openViewModal()
    onClose()
  }

  return (
    <div
      className="manage-views-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="manage-views-modal" role="dialog" aria-modal aria-label="Manage views">
        <div className="manage-views-modal__header">
          <span className="manage-views-modal__title">Manage Views</span>
          <button type="button" className="manage-views-modal__close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="manage-views-modal__body">
          <section className="manage-views-modal__section">
            <div className="manage-views-modal__section-header">
              <span>Quick Filters</span>
              <span className="manage-views-modal__section-hint">Drag to reorder</span>
            </div>
            <div className="manage-views-modal__list">
              {quickFilterOrder.map((filter, index) => (
                <div
                  key={filter}
                  className={`manage-views-modal__row manage-views-modal__row--quick ${dragOverIndex === index ? 'drag-over' : ''} ${dragIndex === index ? 'dragging' : ''}`}
                  draggable
                  onDragStart={() => handleDragStart(index)}
                  onDragOver={(e) => handleDragOver(e, index)}
                  onDrop={(e) => handleDrop(e, index)}
                  onDragEnd={handleDragEnd}
                >
                  <GripVertical size={14} className="manage-views-modal__grip" />
                  <span className={`manage-views-modal__filter-badge manage-views-modal__filter-badge--${QUICK_FILTER_VARIANTS[filter]}`}>
                    {QUICK_FILTER_LABELS[filter]}
                  </span>
                  <Lock size={12} className="manage-views-modal__lock" title="Built-in filter — cannot be edited" />
                </div>
              ))}
              {ALL_QUICK_FILTERS.filter((f) => !quickFilterOrder.includes(f)).length > 0 && (
                <p className="manage-views-modal__note">
                  Some filters are hidden because no categories match them.
                </p>
              )}
            </div>
          </section>

          <section className="manage-views-modal__section">
            <div className="manage-views-modal__section-header">
              <span>Custom Views</span>
              <button
                type="button"
                className="manage-views-modal__add-btn"
                onClick={handleNewView}
              >
                <Plus size={13} />
                New View
              </button>
            </div>
            {(!views || views.length === 0) ? (
              <p className="manage-views-modal__empty">
                No custom views yet. Create one to filter categories by a saved set.
              </p>
            ) : (
              <div className="manage-views-modal__list">
                {views.map((view) => (
                  <div key={view.id} className="manage-views-modal__row">
                    <span className="manage-views-modal__view-name">{view.name}</span>
                    <div className="manage-views-modal__row-actions">
                      <button
                        type="button"
                        className="manage-views-modal__icon-btn"
                        onClick={() => handleEditView(view.id)}
                        title="Edit view"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        type="button"
                        className="manage-views-modal__icon-btn manage-views-modal__icon-btn--danger"
                        onClick={() => handleDeleteView(view.id)}
                        disabled={deleteView.isPending}
                        title="Delete view"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
