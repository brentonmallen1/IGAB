import { useState } from 'react'
import { Check, Eye, EyeOff, Pencil, Trash2, X } from 'lucide-react'
import { useDeleteCategory, useUpdateCategory } from '../../../api/categories'
import type { Category } from '../../../types'
import './CategoryMobileActions.css'
import { confirmAsync } from '../../../stores/confirmStore'

interface Props {
  budgetId: string
  category: Category
  /** Called after a destructive action so the sheet can close */
  onDone: () => void
}

/**
 * Rename / hide / delete for the mobile inspector sheet — these live behind
 * hover on desktop rows, which has no equivalent on touch.
 */
export function CategoryMobileActions({ budgetId, category, onDone }: Props) {
  const updateCategory = useUpdateCategory(budgetId)
  const deleteCategory = useDeleteCategory(budgetId)
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState(category.name)
  const [subtitleValue, setSubtitleValue] = useState(category.subtitle ?? '')

  function commitRename() {
    const name = renameValue.trim()
    const subtitle = subtitleValue.trim() || null
    const changes: { name?: string; subtitle?: string | null } = {}
    if (name && name !== category.name) changes.name = name
    if (subtitle !== (category.subtitle ?? null)) changes.subtitle = subtitle
    if (Object.keys(changes).length > 0) updateCategory.mutate({ id: category.id, ...changes })
    setIsRenaming(false)
  }

  async function handleDelete() {
    const ok = await confirmAsync({
      title: `Delete ${category.name}?`,
      message: 'Transactions will lose their category.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    deleteCategory.mutate(category.id)
    onDone()
  }

  if (isRenaming) {
    return (
      <div className="cat-mobile-actions cat-mobile-actions--renaming">
        <div className="cat-mobile-actions__fields">
          <input
            className="cat-mobile-actions__input"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') setIsRenaming(false)
            }}
            placeholder="Name"
            autoFocus
          />
          <input
            className="cat-mobile-actions__input"
            value={subtitleValue}
            onChange={(e) => setSubtitleValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') setIsRenaming(false)
            }}
            placeholder="Subtitle (optional)"
          />
        </div>
        <button className="cat-mobile-actions__btn" onClick={commitRename} aria-label="Save name">
          <Check size={16} />
        </button>
        <button
          className="cat-mobile-actions__btn"
          onClick={() => setIsRenaming(false)}
          aria-label="Cancel rename"
        >
          <X size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="cat-mobile-actions">
      <button
        className="cat-mobile-actions__btn"
        onClick={() => {
          setRenameValue(category.name)
          setSubtitleValue(category.subtitle ?? '')
          setIsRenaming(true)
        }}
      >
        <Pencil size={14} />
        Rename
      </button>
      <button
        className="cat-mobile-actions__btn"
        onClick={() => updateCategory.mutate({ id: category.id, is_hidden: !category.is_hidden })}
      >
        {category.is_hidden ? <Eye size={14} /> : <EyeOff size={14} />}
        {category.is_hidden ? 'Unhide' : 'Hide'}
      </button>
      <button
        className="cat-mobile-actions__btn cat-mobile-actions__btn--danger"
        onClick={handleDelete}
      >
        <Trash2 size={14} />
        Delete
      </button>
    </div>
  )
}
