import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  useCardEndings,
  useCreateCardEnding,
  useDeleteCardEnding,
  useUpdateCardEnding,
  type CardEnding,
} from '../../api/cardEndings'
import { apiErrorMessage } from '../../api/client'
import './CardEndingsSection.css'

const FOUR_DIGITS = /^\d{4}$/

/**
 * The cards that pay from this account, by their last four digits.
 *
 * A receipt scan reads the ending off the receipt and uses this list to say
 * which account the purchase belongs to. An account holds as many as it
 * needs: a second cardholder's card, a replacement, and a phone wallet's —
 * Apple Pay and Google Pay print a number of their own. An ending belongs to
 * one account; the server refuses a second and names the first.
 *
 * Not a <form>: this sits inside the Account Settings form, like the account
 * numbers above it. Enter is handled here and stopped, so it saves the ending
 * and only the ending.
 */
export function CardEndingsSection({
  budgetId,
  accountId,
}: {
  budgetId: string
  accountId: string
}) {
  const { data: all = [] } = useCardEndings(budgetId)
  const endings = all.filter((e) => e.account_id === accountId)
  const remove = useDeleteCardEnding(budgetId)
  // `null`: nothing open; 'new': the add row; an id: that row in edit.
  const [editing, setEditing] = useState<string | null>(null)

  return (
    <div className="dialog-form__field">
      <span>Card endings</span>
      {endings.length > 0 && (
        <ul className="card-endings">
          {endings.map((ending) =>
            editing === ending.id ? (
              <li key={ending.id}>
                <EndingEditor
                  budgetId={budgetId}
                  accountId={accountId}
                  ending={ending}
                  onDone={() => setEditing(null)}
                />
              </li>
            ) : (
              <li key={ending.id} className="card-endings__row">
                <code className="card-endings__digits">•••• {ending.last4}</code>
                <span className="card-endings__label">{ending.label}</span>
                <button
                  type="button"
                  className="card-endings__icon-btn"
                  onClick={() => setEditing(ending.id)}
                  aria-label={`Edit card ending ${ending.last4}`}
                >
                  <Pencil size={13} />
                </button>
                <button
                  type="button"
                  className="card-endings__icon-btn"
                  onClick={() =>
                    remove.mutate(ending.id, {
                      onError: (err) => toast.error(apiErrorMessage(err, 'Could not remove it')),
                    })
                  }
                  aria-label={`Remove card ending ${ending.last4}`}
                >
                  <Trash2 size={13} />
                </button>
              </li>
            )
          )}
        </ul>
      )}
      {editing === 'new' ? (
        <EndingEditor budgetId={budgetId} accountId={accountId} onDone={() => setEditing(null)} />
      ) : (
        <button
          type="button"
          className="dialog-btn dialog-btn--secondary card-endings__add"
          onClick={() => setEditing('new')}
        >
          <Plus size={13} aria-hidden />
          Add a card ending
        </button>
      )}
      <p className="dialog-form__hint">
        The last four digits of each card that pays from this account. A scanned receipt that shows
        one is matched to this account.
      </p>
    </div>
  )
}

function EndingEditor({
  budgetId,
  accountId,
  ending,
  onDone,
}: {
  budgetId: string
  accountId: string
  ending?: CardEnding
  onDone: () => void
}) {
  const create = useCreateCardEnding(budgetId)
  const update = useUpdateCardEnding(budgetId)
  const [last4, setLast4] = useState(ending?.last4 ?? '')
  const [label, setLabel] = useState(ending?.label ?? '')
  const [error, setError] = useState<string | null>(null)
  const busy = create.isPending || update.isPending

  function save() {
    if (busy) return
    const digits = last4.trim()
    if (!FOUR_DIGITS.test(digits)) {
      setError('Enter the last four digits.')
      return
    }
    const body = { last4: digits, label: label.trim() || null }
    const done = {
      onSuccess: onDone,
      onError: (err: unknown) => setError(apiErrorMessage(err, 'Could not save it')),
    }
    if (ending) update.mutate({ id: ending.id, ...body }, done)
    else create.mutate({ account_id: accountId, ...body }, done)
  }

  return (
    <div
      className="card-endings__editor"
      role="group"
      aria-label={ending ? `Edit card ending ${ending.last4}` : 'Add a card ending'}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && e.target instanceof HTMLInputElement) {
          e.preventDefault()
          save()
        } else if (e.key === 'Escape') {
          e.stopPropagation()
          onDone()
        }
      }}
    >
      <div className="card-endings__inputs">
        <input
          className="card-endings__last4"
          value={last4}
          onChange={(e) => {
            setLast4(e.target.value.replace(/\D/g, '').slice(0, 4))
            setError(null)
          }}
          inputMode="numeric"
          placeholder="4417"
          aria-label="Last four digits"
          autoComplete="off"
          autoFocus
        />
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Whose card, or Apple Pay (optional)"
          aria-label="Label"
          maxLength={60}
          autoComplete="off"
        />
      </div>
      {error && <p className="dialog-form__error">{error}</p>}
      <div className="card-endings__actions">
        <button
          type="button"
          className="dialog-btn dialog-btn--secondary"
          disabled={busy}
          onClick={save}
        >
          {busy ? 'Saving…' : ending ? 'Save' : 'Add'}
        </button>
        <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onDone}>
          Cancel
        </button>
      </div>
    </div>
  )
}
