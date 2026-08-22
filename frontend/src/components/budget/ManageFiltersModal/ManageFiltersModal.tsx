import { useState } from 'react'
import { X, GripVertical, Pencil, Trash2, Plus, Lock, ChevronUp, ChevronDown } from 'lucide-react'
import { useBudgetFilters, useDeleteBudgetFilter } from '../../../api/budgetFilters'
import { useUIStore, ALL_QUICK_FILTERS } from '../../../stores/uiStore'
import type { QuickFilter } from '../../../stores/uiStore'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import './ManageFiltersModal.css'

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

export function ManageFiltersModal({ budgetId, onClose }: Props) {
  const { data: filters } = useBudgetFilters(budgetId)
  const deleteFilter = useDeleteBudgetFilter(budgetId)
  const openModal = useUIStore((s) => s.openModal)
  const quickFilterOrder = useUIStore((s) => s.quickFilterOrder)
  const reorderQuickFilters = useUIStore((s) => s.reorderQuickFilters)
  const activeFilterId = useUIStore((s) => s.activeFilterId)
  const setActiveFilter = useUIStore((s) => s.setActiveFilter)

  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)
  const trapRef = useFocusTrap<HTMLDivElement>(onClose)

  function moveFilter(index: number, delta: -1 | 1) {
    const target = index + delta
    if (target < 0 || target >= quickFilterOrder.length) return
    const next = [...quickFilterOrder]
    const [moved] = next.splice(index, 1)
    next.splice(target, 0, moved)
    reorderQuickFilters(next)
  }

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

  async function handleDeleteFilter(id: string) {
    await deleteFilter.mutateAsync(id)
    if (activeFilterId === id) setActiveFilter(null)
  }

  function handleEditFilter(id: string) {
    openModal('filter', id)
    onClose()
  }

  function handleNewFilter() {
    openModal('filter')
    onClose()
  }

  return (
    <div
      className="manage-filters-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div ref={trapRef} tabIndex={-1} className="manage-filters-modal" role="dialog" aria-modal aria-label="Manage filters">
        <div className="manage-filters-modal__header">
          <span className="manage-filters-modal__title">Manage Filters</span>
          <button type="button" className="manage-filters-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="manage-filters-modal__body">
          <section className="manage-filters-modal__section">
            <div className="manage-filters-modal__section-header">
              <span>Quick Filters</span>
              <span className="manage-filters-modal__section-hint">Drag or use arrows to reorder</span>
            </div>
            <div className="manage-filters-modal__list">
              {quickFilterOrder.map((filter, index) => (
                <div
                  key={filter}
                  className={`manage-filters-modal__row manage-filters-modal__row--quick ${dragOverIndex === index ? 'drag-over' : ''} ${dragIndex === index ? 'dragging' : ''}`}
                  draggable
                  onDragStart={() => handleDragStart(index)}
                  onDragOver={(e) => handleDragOver(e, index)}
                  onDrop={(e) => handleDrop(e, index)}
                  onDragEnd={handleDragEnd}
                >
                  <GripVertical size={14} className="manage-filters-modal__grip" />
                  <span className={`manage-filters-modal__filter-badge manage-filters-modal__filter-badge--${QUICK_FILTER_VARIANTS[filter]}`}>
                    {QUICK_FILTER_LABELS[filter]}
                  </span>
                  <span
                    className="manage-filters-modal__lock"
                    style={{ display: 'inline-flex' }}
                    title="Built-in filter — cannot be edited"
                  >
                    <Lock size={12} />
                  </span>
                  <div className="manage-filters-modal__row-actions">
                    <button
                      type="button"
                      className="manage-filters-modal__icon-btn"
                      onClick={() => moveFilter(index, -1)}
                      disabled={index === 0}
                      aria-label={`Move ${QUICK_FILTER_LABELS[filter]} up`}
                      title="Move up"
                    >
                      <ChevronUp size={13} />
                    </button>
                    <button
                      type="button"
                      className="manage-filters-modal__icon-btn"
                      onClick={() => moveFilter(index, 1)}
                      disabled={index === quickFilterOrder.length - 1}
                      aria-label={`Move ${QUICK_FILTER_LABELS[filter]} down`}
                      title="Move down"
                    >
                      <ChevronDown size={13} />
                    </button>
                  </div>
                </div>
              ))}
              {ALL_QUICK_FILTERS.filter((f) => !quickFilterOrder.includes(f)).length > 0 && (
                <p className="manage-filters-modal__note">
                  Some filters are hidden because no categories match them.
                </p>
              )}
            </div>
          </section>

          <section className="manage-filters-modal__section">
            <div className="manage-filters-modal__section-header">
              <span>Saved Filters</span>
              <button
                type="button"
                className="manage-filters-modal__add-btn"
                onClick={handleNewFilter}
              >
                <Plus size={13} />
                New Filter
              </button>
            </div>
            {(!filters || filters.length === 0) ? (
              <p className="manage-filters-modal__empty">
                No custom filters yet. Create one to filter categories by a saved set.
              </p>
            ) : (
              <div className="manage-filters-modal__list">
                {filters.map((saved) => (
                  <div key={saved.id} className="manage-filters-modal__row">
                    <span className="manage-filters-modal__filter-name">{saved.name}</span>
                    <div className="manage-filters-modal__row-actions">
                      <button
                        type="button"
                        className="manage-filters-modal__icon-btn"
                        onClick={() => handleEditFilter(saved.id)}
                        aria-label={`Edit filter ${saved.name}`}
                        title="Edit filter"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        type="button"
                        className="manage-filters-modal__icon-btn manage-filters-modal__icon-btn--danger"
                        onClick={() => handleDeleteFilter(saved.id)}
                        disabled={deleteFilter.isPending}
                        aria-label={`Delete filter ${saved.name}`}
                        title="Delete filter"
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
