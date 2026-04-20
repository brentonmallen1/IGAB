import { useState, useEffect } from 'react'
import { useUpdateCategory } from '../../../api/categories'
import type { Category } from '../../../types'

interface Props {
  category: Category
  budgetId: string
}

export function CategoryNotesSection({ category, budgetId }: Props) {
  const [note, setNote] = useState(category.note ?? '')
  const update = useUpdateCategory(budgetId)

  useEffect(() => {
    setNote(category.note ?? '')
  }, [category.id, category.note])

  function handleBlur() {
    const trimmed = note.trim()
    if (trimmed !== (category.note ?? '')) {
      update.mutate({ id: category.id, note: trimmed || null })
    }
  }

  return (
    <div className="inspector-section">
      <div className="inspector-section__title">Notes</div>
      <textarea
        className="inspector-notes"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onBlur={handleBlur}
        placeholder="Enter a note…"
        rows={3}
      />
    </div>
  )
}
