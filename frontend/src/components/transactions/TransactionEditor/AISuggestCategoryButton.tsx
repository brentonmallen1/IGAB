import { Sparkles } from 'lucide-react'
import { useSuggestCategory } from '../../../api/ai'

interface Props {
  budgetId: string
  payeeName: string
  /** The boxes' amount in dollars, or null when nothing usable is typed. */
  dollars: number | null
  memo: string
  /** Called with the model's pick, which counts as the person's own choice. */
  onSuggest: (categoryId: string) => void
}

/** The editor's "AI Suggest" beside the category field. */
export function AISuggestCategoryButton({ budgetId, payeeName, dollars, memo, onSuggest }: Props) {
  const suggestCategory = useSuggestCategory(budgetId)
  return (
    <button
      type="button"
      className="txn-editor__ai-btn"
      title="AI suggest category"
      disabled={suggestCategory.isPending}
      onClick={async () => {
        const result = await suggestCategory.mutateAsync({
          payee_name: payeeName || 'Unknown',
          // A hint, not a save: with nothing usable in the boxes the model
          // is asked about the payee alone.
          amount: dollars ?? 0,
          memo: memo || undefined,
        })
        if (result.category_id) onSuggest(result.category_id)
      }}
    >
      <Sparkles size={12} />
      {suggestCategory.isPending ? 'Thinking…' : 'AI Suggest'}
    </button>
  )
}
