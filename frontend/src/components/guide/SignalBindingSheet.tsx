import { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  useConceptCandidates,
  useSetBinding,
  type ConceptInfo,
  type EntityType,
  type Signal,
} from '../../api/guide'
import { GuideDialog } from './GuideDialog'

/**
 * Correcting what the app decided about one concept.
 *
 * Four things a person might want to say, and the sheet has to make all four
 * equally easy:
 *
 *   "you found the wrong thing"  → point it at the right categories/accounts
 *   "I have this, just not here" → declare an amount held outside IGAB
 *   "stop tracking this"         → dismiss it
 *   "use your own guess again"   → reset to automatic
 *
 * The first two combine: an emergency fund half here and half at another bank
 * is the ordinary arrangement, so binding and declaring are not exclusive.
 */
export function SignalBindingSheet({
  budgetId,
  concept,
  signal,
  onClose,
}: {
  budgetId: string
  concept: ConceptInfo
  signal: Signal | undefined
  onClose: () => void
}) {
  const { data: candidates } = useConceptCandidates(budgetId, concept.key)
  const setBinding = useSetBinding(budgetId)

  // Seeded from whatever is stored so the sheet opens showing the current
  // answer rather than a blank form the user has to reconstruct. Initialised
  // rather than synced by an effect: the sheet is mounted fresh each time it
  // opens, so the props are already there on the first render.
  const [selected, setSelected] = useState<Partial<Record<EntityType, string[]>>>(
    () => signal?.entities ?? {}
  )
  const [external, setExternal] = useState(() => signal?.external_declared ?? false)
  const [amount, setAmount] = useState(() => signal?.external_value ?? '')
  const [note, setNote] = useState(() => signal?.note ?? '')

  const answered = concept.kind === 'boolean' && concept.binds_to.length === 0

  const hasSelection = useMemo(
    () => Object.values(selected).some((ids) => (ids?.length ?? 0) > 0),
    [selected]
  )

  function toggle(type: EntityType, id: string) {
    setSelected((prev) => {
      const current = prev[type] ?? []
      return {
        ...prev,
        [type]: current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
      }
    })
  }

  async function save(mode: 'manual' | 'dismissed' | 'auto' | 'answer', answer?: boolean) {
    try {
      await setBinding.mutateAsync({
        conceptKey: concept.key,
        mode,
        entity_ids: mode === 'manual' ? selected : undefined,
        answer,
        external: mode === 'manual' ? external : false,
        external_amount: external && amount.trim() ? amount.trim() : null,
        note: note.trim() || null,
      })
      onClose()
    } catch {
      toast.error('Could not save that. Please try again.')
    }
  }

  return (
    <GuideDialog title={concept.label} onClose={onClose} historyKey="guide-binding">
      <p className="dialog__body">{concept.prompt}</p>
      {concept.caveat && (
        <p className="dialog__body dialog__body--muted">{concept.caveat}</p>
      )}

      {answered ? (
        <div className="binding__answers">
          <button type="button" className="guide-branch" onClick={() => save('answer', true)}>
            <span className="guide-branch__answer">Yes</span>
            <span className="guide-branch__label">This applies to me</span>
          </button>
          <button type="button" className="guide-branch" onClick={() => save('answer', false)}>
            <span className="guide-branch__answer">No</span>
            <span className="guide-branch__label">It does not</span>
          </button>
        </div>
      ) : (
        <>
          {concept.binds_to.map((type) => {
            const options = candidates?.[type] ?? []
            if (!options.length) return null
            return (
              <fieldset key={type} className="binding__group">
                <legend className="binding__legend">{GROUP_LABEL[type]}</legend>
                <div className="binding__options">
                  {options.map((option) => (
                    <label key={option.id} className="binding__option">
                      <input
                        type="checkbox"
                        checked={(selected[type] ?? []).includes(option.id)}
                        onChange={() => toggle(type, option.id)}
                      />
                      <span className="binding__option-name">{option.name}</span>
                      {option.detail && (
                        <span className="binding__option-detail">{option.detail}</span>
                      )}
                    </label>
                  ))}
                </div>
              </fieldset>
            )
          })}

          {concept.allows_external && (
            <div className="binding__external">
              <label className="binding__option">
                <input
                  type="checkbox"
                  checked={external}
                  onChange={(e) => setExternal(e.target.checked)}
                />
                <span className="binding__option-name">I also hold some of this elsewhere</span>
              </label>
              {external && (
                <div className="binding__external-fields">
                  <label className="binding__field">
                    <span>Amount (optional)</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      placeholder="Leave blank if you would rather not say"
                    />
                  </label>
                  <label className="binding__field">
                    <span>Note (optional)</span>
                    <input
                      type="text"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="e.g. credit union, not tracked here"
                    />
                  </label>
                  <p className="binding__caveat">
                    We will show this as something you told us, dated today. It never counts
                    towards net worth or any report — those come from your transactions only.
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="binding__actions">
            <button
              type="button"
              className="binding__save"
              disabled={setBinding.isPending || (!hasSelection && !external)}
              onClick={() => save('manual')}
            >
              Save
            </button>
            {signal?.source !== 'auto' && (
              <button type="button" className="guide-link-button" onClick={() => save('auto')}>
                Reset to automatic
              </button>
            )}
            <button
              type="button"
              className="guide-link-button binding__dismiss"
              onClick={() => save('dismissed')}
            >
              Don&rsquo;t track this
            </button>
          </div>
        </>
      )}
    </GuideDialog>
  )
}

const GROUP_LABEL: Record<EntityType, string> = {
  category: 'Categories',
  account: 'Accounts',
  liability: 'Debts',
}
