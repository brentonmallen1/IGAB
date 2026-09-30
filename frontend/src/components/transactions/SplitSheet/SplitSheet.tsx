import { useMemo, useState, type MouseEvent } from 'react'
import { ChevronRight, Plus, Trash2 } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import {
  SelectionSheet,
  type SelectionSheetOption,
} from '../../common/SelectionSheet/SelectionSheet'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { useFormatters } from '../../../hooks/useFormatters'
import { canRemoveSplitLine, checkSplit, coverRemainder } from '../../../utils/splits'
import { expressionToCents } from '../../../utils/amountExpression'
import { randomUUID } from '../../../utils/uuid'
import type { SplitDraft } from '../../../stores/transactionEditStore'
import { splitProgress, splitStatus } from './splitSummary'
import './SplitSheet.css'

/** Which picker is up: a line's category, or where the rest goes. One
 *  SelectionSheet serves both — two stacked on a phone fight for it. */
type Picker = { kind: 'leg'; tempId: string } | { kind: 'cover' } | null

interface Props {
  open: boolean
  /** Done, back, or a swipe: the lines stay as they are. */
  onClose: () => void
  /** The parent's magnitude, in cents — what the lines must add up to. */
  totalCents: number
  legs: SplitDraft[]
  onChange: (legs: SplitDraft[]) => void
  /** The filing categories, hints included (Available, where the host knows it). */
  categoryOptions: SelectionSheetOption[]
  /** False on a tracking account: its rows carry no category. */
  canCategorize: boolean
  /** Stop splitting — the host puts the first line's category back. Absent
   *  for a split already saved: un-splitting that is not an edit here. */
  onUnsplit?: () => void
}

/** A line still missing its category (where it takes one) or its amount. */
function firstUnfinished(legs: SplitDraft[], canCategorize: boolean): string | null {
  const leg = legs.find(
    (l) => (canCategorize && !l.categoryId) || isNaN(expressionToCents(l.amount))
  )
  return leg?.tempId ?? null
}

/** A folded line's amount: formatted when it reads, as typed when it does
 *  not (unreadable is not zero), and nothing when blank. */
function legAmountText(amount: string, money: (cents: number) => string): string | null {
  if (!amount.trim()) return null
  const cents = expressionToCents(amount)
  return isNaN(cents) ? amount : money(cents)
}

function focusField(e: MouseEvent<HTMLElement>) {
  e.currentTarget.querySelector('input')?.focus()
}

/**
 * A split, on a phone, with the whole screen to itself.
 *
 * Inline in a form the lines were a cramped list under fields that scrolled
 * around them, with the total out of sight and a desktop dropdown for each
 * category. Here the total and what is left stay pinned at the top, every
 * line folds to one row and opens to its category, amount and memo, and "Cover the rest"
 * puts whatever is left into one envelope in a single choice. Quick add and
 * the editor both open this, so a phone has one split editor.
 */
export function SplitSheet({
  open,
  onClose,
  totalCents,
  legs,
  onChange,
  categoryOptions,
  canCategorize,
  onUnsplit,
}: Props) {
  const { formatMoney } = useFormatters()
  const [picker, setPicker] = useState<Picker>(null)
  // One line open at a time; the rest fold to a row each. The extra tap is
  // the point: a line is changed on purpose, never by a stray touch while
  // scrolling past it. Each time the sheet opens, the first unfinished line
  // starts open, so a new split does not cost a tap per line.
  const [openId, setOpenId] = useState<string | null>(null)
  const [wasOpen, setWasOpen] = useState(false)
  if (open !== wasOpen) {
    setWasOpen(open)
    if (open) setOpenId(firstUnfinished(legs, canCategorize))
  }

  const check = checkSplit(totalCents, legs)
  const status = splitStatus(check, formatMoney)
  const optionById = useMemo(
    () => new Map(categoryOptions.map((o) => [o.id, o])),
    [categoryOptions]
  )
  const money = (cents: number) => formatMoney(cents / 100)

  function update(tempId: string, patch: Partial<Omit<SplitDraft, 'tempId'>>) {
    onChange(legs.map((l) => (l.tempId === tempId ? { ...l, ...patch } : l)))
  }

  const newLeg = (): SplitDraft => ({
    tempId: randomUUID(),
    amount: '',
    categoryId: null,
    memo: '',
  })

  // The cover picker: categories already in the split first, each saying
  // what its line becomes; everything else below.
  const inSplit = legs.flatMap((l) => {
    if (!l.categoryId) return []
    const had = expressionToCents(l.amount)
    const from = isNaN(had) ? 0 : had
    return [
      {
        id: l.categoryId,
        label: optionById.get(l.categoryId)?.label ?? '',
        hint: `${money(from)} → ${money(from + check.remainingCents)}`,
      },
    ]
  })
  const inSplitIds = new Set(inSplit.map((o) => o.id))
  const coverable = canCategorize && check.remainingCents > 0 && check.totalCents > 0

  const pickerLeg = picker?.kind === 'leg' ? legs.find((l) => l.tempId === picker.tempId) : null

  return (
    <>
      <BottomSheet
        open={open}
        onClose={onClose}
        title={`Split ${money(check.totalCents)}`}
        height="full"
        historyKey="split-sheet"
        closeLabel="Done"
        footer={
          <div className="split-sheet__footer">
            {coverable && (
              <button
                type="button"
                className="split-sheet__cover"
                onClick={() => {
                  setOpenId(null)
                  setPicker({ kind: 'cover' })
                }}
              >
                Cover the remaining {money(check.remainingCents)}…
              </button>
            )}
            <button type="button" className="split-sheet__done" onClick={onClose}>
              Done
            </button>
          </div>
        }
      >
        <div className="split-sheet">
          <div className="split-sheet__status">
            <div className="split-sheet__status-line">
              <span>
                Split <strong>{money(check.assignedCents)}</strong> of {money(check.totalCents)}
              </span>
              <span className={`split-sheet__tone split-sheet__tone--${status.tone}`} role="status">
                {status.text}
              </span>
            </div>
            <div className="split-sheet__bar" aria-hidden>
              <div
                className={`split-sheet__bar-fill split-sheet__tone-bg--${status.tone}`}
                style={{ width: `${splitProgress(check)}%` }}
              />
            </div>
          </div>

          <ol className="split-sheet__legs">
            {legs.map((leg, i) => {
              const option = leg.categoryId ? optionById.get(leg.categoryId) : undefined
              const n = i + 1
              if (leg.tempId !== openId) {
                const amount = legAmountText(leg.amount, money)
                return (
                  <li key={leg.tempId}>
                    <button
                      type="button"
                      className="split-sheet__row"
                      aria-expanded={false}
                      aria-label={`Split ${n}: ${option?.label ?? 'no category'}, ${amount ?? 'no amount'}`}
                      onClick={() => setOpenId(leg.tempId)}
                    >
                      <span className="split-sheet__row-text">
                        <span
                          className={`split-sheet__cat-name ${option || !canCategorize ? '' : 'split-sheet__cat-name--empty'}`}
                        >
                          {canCategorize ? (option?.label ?? 'Choose category') : `Line ${n}`}
                        </span>
                        <span className="split-sheet__cat-hint">
                          {leg.memo ||
                            (option?.hint ? `Available ${option.hint}` : 'Tap to fill in')}
                        </span>
                      </span>
                      <span
                        className={`split-sheet__row-amount ${amount ? '' : 'split-sheet__row-amount--empty'}`}
                      >
                        {amount ?? '—'}
                      </span>
                    </button>
                  </li>
                )
              }
              return (
                <li key={leg.tempId} className="split-sheet__leg">
                  {canCategorize && (
                    <button
                      type="button"
                      className="split-sheet__cat"
                      aria-label={`Split ${n} category`}
                      onClick={() => setPicker({ kind: 'leg', tempId: leg.tempId })}
                    >
                      <span className="split-sheet__cat-text">
                        <span
                          className={`split-sheet__cat-name ${option ? '' : 'split-sheet__cat-name--empty'}`}
                        >
                          {option?.label ?? 'Choose category'}
                        </span>
                        {option?.hint && (
                          <span className="split-sheet__cat-hint">Available {option.hint}</span>
                        )}
                      </span>
                      <ChevronRight size={16} aria-hidden />
                    </button>
                  )}
                  {/* Not a <label>: the input's own name says which line it is, and a
                      second "Amount" label would shadow the form's. A tap on the
                      word still lands in the field. */}
                  <div className="split-sheet__field" onClick={focusField}>
                    <span className="split-sheet__field-label" aria-hidden>
                      Amount
                    </span>
                    <AmountInput
                      className="split-sheet__amount"
                      value={leg.amount}
                      onValueChange={(v) => update(leg.tempId, { amount: v })}
                      placeholder="0.00"
                      aria-label={`Split ${n} amount`}
                    />
                  </div>
                  <div className="split-sheet__field" onClick={focusField}>
                    <span className="split-sheet__field-label" aria-hidden>
                      Memo
                    </span>
                    <input
                      type="text"
                      className="split-sheet__memo"
                      value={leg.memo}
                      onChange={(e) => update(leg.tempId, { memo: e.target.value })}
                      placeholder="Optional"
                      enterKeyHint="done"
                      aria-label={`Split ${n} memo`}
                    />
                  </div>
                  <div className="split-sheet__leg-actions">
                    <button
                      type="button"
                      className="split-sheet__remove"
                      onClick={() => {
                        setOpenId(null)
                        onChange(legs.filter((l) => l.tempId !== leg.tempId))
                      }}
                      disabled={!canRemoveSplitLine(legs.length)}
                      aria-label={`Remove split ${n}`}
                    >
                      <Trash2 size={15} aria-hidden />
                      Remove line
                    </button>
                    <button
                      type="button"
                      className="split-sheet__fold"
                      onClick={() => setOpenId(null)}
                    >
                      Done with line
                    </button>
                  </div>
                </li>
              )
            })}
          </ol>
          {legs.length === 1 && (
            <p className="split-sheet__single">One line saves as a single category, not a split.</p>
          )}

          <button
            type="button"
            className="split-sheet__add"
            onClick={() => {
              const leg = newLeg()
              onChange([...legs, leg])
              setOpenId(leg.tempId)
            }}
          >
            <Plus size={15} aria-hidden />
            Add line
          </button>
          {onUnsplit && (
            <button type="button" className="split-sheet__unsplit" onClick={onUnsplit}>
              Don't split this transaction
            </button>
          )}
        </div>
      </BottomSheet>

      <SelectionSheet
        open={picker !== null}
        onClose={() => setPicker(null)}
        title={
          picker?.kind === 'cover'
            ? `Cover the remaining ${money(check.remainingCents)}`
            : 'Split category'
        }
        options={
          picker?.kind === 'cover'
            ? categoryOptions.filter((o) => !inSplitIds.has(o.id))
            : categoryOptions
        }
        topSection={
          picker?.kind === 'cover' && inSplit.length > 0
            ? { label: 'Add to a line in this split', options: inSplit }
            : undefined
        }
        // The cover picker is a question: nothing is chosen until it is answered.
        value={picker?.kind === 'cover' ? undefined : (pickerLeg?.categoryId ?? null)}
        onChange={(id) => {
          if (picker?.kind === 'cover') {
            if (id) onChange(coverRemainder(legs, check.remainingCents, id, newLeg))
          } else if (picker?.kind === 'leg') {
            update(picker.tempId, { categoryId: id })
          }
        }}
        allowNone={picker?.kind === 'leg'}
        noneLabel="No category"
        placeholder="Search categories…"
      />
    </>
  )
}
