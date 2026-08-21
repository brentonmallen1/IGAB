import { useState, useRef } from 'react'
import { Tag, CheckCircle, Trash2, MoreHorizontal, ThumbsUp, GitMerge, Paperclip, Pencil } from 'lucide-react'
import { ContextMenu, type ContextMenuItem } from '../../common/ContextMenu/ContextMenu'
import { Combobox, type ComboboxOption } from '../../common/Combobox/Combobox'
import { FloatingSelectionBar } from '../../common/FloatingSelectionBar/FloatingSelectionBar'
import { useFormatters } from '../../../hooks/useFormatters'
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
  onAttachments?: () => void
  onEdit?: () => void
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
  onAttachments,
  onEdit,
}: Props) {
  const { formatMoney } = useFormatters()
  const [showCategoryPicker, setShowCategoryPicker] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [morePos, setMorePos] = useState({ x: 0, y: 0 })
  const moreRef = useRef<HTMLButtonElement>(null)

  const totalClass = selectedTotal < 0 ? 'negative' : selectedTotal > 0 ? 'positive' : ''

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
    <FloatingSelectionBar
      label={`${selectedCount} Transaction${selectedCount !== 1 ? 's' : ''}`}
      sublabel={<span className={`sab__total sab__total--${totalClass}`}>{formatMoney(selectedTotal)}</span>}
      onClose={onClear}
    >
      {onEdit && selectedCount === 1 && (
        <FloatingSelectionBar.Button onClick={onEdit} title="Edit transaction details">
          <Pencil size={14} />
          Edit
        </FloatingSelectionBar.Button>
      )}

      <div className="sab__categorize">
        {showCategoryPicker ? (
          <div className="sab__category-picker">
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
          <FloatingSelectionBar.Button onClick={() => setShowCategoryPicker(true)}>
            <Tag size={14} />
            Categorize
          </FloatingSelectionBar.Button>
        )}
      </div>

      <FloatingSelectionBar.Button onClick={() => onSetCleared('cleared')} title="Mark cleared">
        <CheckCircle size={14} />
        Clear
      </FloatingSelectionBar.Button>

      {onApprove && (
        <FloatingSelectionBar.Button onClick={onApprove} title="Approve transactions">
          <ThumbsUp size={14} />
          Approve
        </FloatingSelectionBar.Button>
      )}

      {canMerge && onMerge && (
        <FloatingSelectionBar.Button onClick={onMerge} title="Merge selected transactions">
          <GitMerge size={14} />
          Merge
        </FloatingSelectionBar.Button>
      )}

      {onAttachments && selectedCount === 1 && (
        <FloatingSelectionBar.Button onClick={onAttachments} title="Manage attachments">
          <Paperclip size={14} />
          Attachments
        </FloatingSelectionBar.Button>
      )}

      <FloatingSelectionBar.Divider />

      <button
        ref={moreRef}
        className="fsb__btn"
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
    </FloatingSelectionBar>
  )
}
