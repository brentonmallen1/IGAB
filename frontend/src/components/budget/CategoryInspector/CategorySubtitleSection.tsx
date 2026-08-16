import { useState, useEffect } from 'react'
import { useUpdateCategory } from '../../../api/categories'
import type { Category } from '../../../types'

interface Props {
  category: Category
  budgetId: string
}

/**
 * Edit the category's subtitle — the muted annotation shown after the name
 * on the budget page (e.g. a funding reminder like "$457").
 */
export function CategorySubtitleSection({ category, budgetId }: Props) {
  const [subtitle, setSubtitle] = useState(category.subtitle ?? '')
  const update = useUpdateCategory(budgetId)

  useEffect(() => {
    setSubtitle(category.subtitle ?? '')
  }, [category.id, category.subtitle])

  function handleBlur() {
    const trimmed = subtitle.trim()
    if (trimmed !== (category.subtitle ?? '')) {
      update.mutate({ id: category.id, subtitle: trimmed || null })
    }
  }

  return (
    <div className="inspector-section">
      <div className="inspector-section__title">Subtitle</div>
      <input
        className="inspector-subtitle-input"
        value={subtitle}
        onChange={(e) => setSubtitle(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        }}
        placeholder="Shown after the name, e.g. $457"
        maxLength={100}
      />
    </div>
  )
}
