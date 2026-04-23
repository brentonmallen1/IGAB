import { useState, useRef } from 'react'
import { X, Tag, CheckCircle, Trash2, MoreHorizontal, ThumbsUp, GitMerge } from 'lucide-react'
import { ContextMenu, type ContextMenuItem } from '../../common/ContextMenu/ContextMenu'
import { Combobox, type ComboboxOption } from '../../common/Combobox/Combobox'
import { formatMoney } from '../../../utils/money'
import type { ClearedStatus } from '../../../types'
import './SelectionActionBar.css'

interface Props {
  selectedCount: number
  selectedTotal: number
  categoryOptions: ComboboxOption[]
  onCategorize: (categoryId: string) => void
  onSetCleared: (status: ClearedStatus) => void
  onDelete: () => void
  onDuplicate: () => void
  onClear: () => void
  onApprove?: () => void
  onMerge?: () => void
  canMerge?: boolean
}

const MORE_ITEMS: ContextMenuItem[] = [
  { id: 'mark_cleared', label: 'Mark Cleared' },
  { id: 'mark_uncleared', label: 'Mark Uncleared' },
  { id: 'duplicate', label: 'Duplicate' },
  { id: 'separator', label: '', separator: true },
  { id: 'delete', label: 'Delete Selected', danger: true, icon: Trash2 },
]

export function SelectionActionBar({
  selectedCount,
  selectedTotal,
  categoryOptions,
  onCategorize,
  onSetCleared,
  onDelete,
  onDuplicate,
  onClear,
  onApprove,
  onMerge,
  canMerge,
}: Props) {
  const [showCategoryPicker, setShowCategoryPicker] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [morePos, setMorePos] = useState({ x: 0, y: 0 })
  const moreRef = useRef<HTMLButtonElement>(null)

  function handleMoreClick() {
    const rect = moreRef.current?.getBoundingClientRect()
    if (rect) setMorePos({ x: rect.left, y: rect.top - 10 })
    setMoreOpen(true)
  }

  function handleMoreAction(id: string) {
    switch (id) {
      case 'mark_cleared': onSetCleared('cleared'); break
      case 'mark_uncleared': onSetCleared('uncleared'); break
      case 'duplicate': onDuplicate(); break
      case 'delete': onDelete(); break
    }
  }

  return (
    <div className="selection-bar">
      <button className="selection-bar__close" onClick={onClear} title="Clear selection">
        <X size={14} />
      </button>

      <span className="selection-bar__count">
        {selectedCount} Transaction{selectedCount !== 1 ? 's' : ''}
      </span>

      <span className={`selection-bar__total ${selectedTotal < 0 ? 'selection-bar__total--negative' : selectedTotal > 0 ? 'selection-bar__total--positive' : ''}`}>
        {formatMoney(selectedTotal)}
      </span>

      <div className="selection-bar__divider" />

      <div className="selection-bar__action">
        {showCategoryPicker ? (
          <div className="selection-bar__category-picker">
            <Combobox
              value={null}
              options={categoryOptions}
              onChange={(id) => {
                if (id) { onCategorize(id); setShowCategoryPicker(false) }
              }}
              placeholder="Choose category…"
              autoFocus
              onBlurClose={() => setShowCategoryPicker(false)}
            />
          </div>
        ) : (
          <button
            className="selection-bar__btn"
            onClick={() => setShowCategoryPicker(true)}
          >
            <Tag size={14} />
            Categorize
          </button>
        )}
      </div>

      <button
        className="selection-bar__btn"
        onClick={() => onSetCleared('cleared')}
        title="Mark cleared"
      >
        <CheckCircle size={14} />
        Clear
      </button>

      {onApprove && (
        <button
          className="selection-bar__btn"
          onClick={onApprove}
          title="Approve transactions"
        >
          <ThumbsUp size={14} />
          Approve
        </button>
      )}

      {canMerge && onMerge && (
        <button
          className="selection-bar__btn"
          onClick={onMerge}
          title="Merge selected transactions"
        >
          <GitMerge size={14} />
          Merge
        </button>
      )}

      <div className="selection-bar__divider" />

      <button
        ref={moreRef}
        className="selection-bar__btn selection-bar__btn--more"
        onClick={handleMoreClick}
      >
        <MoreHorizontal size={14} />
        More
      </button>

      {moreOpen && (
        <ContextMenu
          items={MORE_ITEMS}
          onSelect={handleMoreAction}
          onClose={() => setMoreOpen(false)}
          position={{ x: morePos.x, y: morePos.y - 160 }}
        />
      )}
    </div>
  )
}
