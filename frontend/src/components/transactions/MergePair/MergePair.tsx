import { ArrowDown } from 'lucide-react'
import { useFormatters } from '../../../hooks/useFormatters'
import { useTransactionSplits } from '../../../api/transactions'
import type { MergeField, MergeKeep, MergePreview, Transaction } from '../../../types'
import { categoryDisplay, type NamedCategory } from '../../../utils/categoryLabels'
import { Tooltip } from '../../common/Tooltip/Tooltip'
import { categoryCellHover, categoryCellLabel, categoryCellText } from '../categoryCell'
import { hasChoices, isKept, pick, pickAll, suppliesAll } from './mergePicks'
import './MergePair.css'

interface Props {
  rows: [Transaction, Transaction]
  /** What to call each card — see `pairLabels`. */
  labels: [string, string]
  /** The server's answer for the current picks; undefined while it is asked. */
  preview: MergePreview | undefined
  /** Why the server would refuse this merge, when it would. */
  refusal: string | null
  keep: MergeKeep
  onKeepChange: (keep: MergeKeep) => void
  payeeMap: ReadonlyMap<string, string>
  categoryLabels: ReadonlyMap<string, NamedCategory>
  accountOnBudget: boolean
}

type Money = (amount: number) => string

const signed = (amount: number, formatMoney: Money) =>
  amount < 0 ? `-${formatMoney(Math.abs(amount))}` : formatMoney(amount)

/** A split's lines, named: the part of a merge the old dialog never showed. */
function Lines({
  lines,
  categoryLabels,
  formatMoney,
}: {
  lines: { amount: number; category_id: string | null }[]
  categoryLabels: ReadonlyMap<string, NamedCategory>
  formatMoney: Money
}) {
  return (
    <ul className="merge-pair__lines">
      {lines.map((line, i) => (
        <li key={i} className="merge-pair__line">
          <span className="merge-pair__line-name">
            {line.category_id ? categoryDisplay(line.category_id, categoryLabels).name : '—'}
          </span>
          <span className="tabular">{formatMoney(Math.abs(line.amount))}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * One value on a card. Where the preview says the field is a choice it is a
 * button that says whether this row's value is the one being kept; anywhere
 * else it is plain text, because there is nothing to decide.
 */
function Value({
  field,
  row,
  other,
  preview,
  keep,
  onKeepChange,
  name,
  children,
}: {
  field: MergeField
  row: Transaction
  other: Transaction
  preview: MergePreview | undefined
  keep: MergeKeep
  onKeepChange: (keep: MergeKeep) => void
  /** The field, as the button's accessible name reads it. */
  name: string
  children: React.ReactNode
}) {
  const choice = preview?.choices[field]
  if (!choice?.choosable) return <span className="merge-pair__value">{children}</span>
  const kept = isKept(choice, row.id)
  return (
    <button
      type="button"
      // A memo is each-or-both; the rest are one-or-the-other.
      role={field === 'memo' ? 'checkbox' : 'radio'}
      aria-checked={kept}
      aria-label={`Keep this ${name}`}
      className={`merge-pair__value merge-pair__pick ${kept ? 'merge-pair__pick--kept' : ''}`}
      onClick={() => onKeepChange(pick(keep, field, choice, row.id, other.id))}
    >
      {children}
    </button>
  )
}

function Card({
  row,
  other,
  label,
  preview,
  keep,
  onKeepChange,
  payeeMap,
  categoryLabels,
  accountOnBudget,
}: Omit<Props, 'rows' | 'labels' | 'refusal'> & {
  row: Transaction
  other: Transaction
  label: string
}) {
  const { formatMoney, formatDate } = useFormatters()
  const { data: lines } = useTransactionSplits(row.id, row.is_split)
  const category = categoryCellLabel(row, categoryLabels, accountOnBudget)
  const pickable = { row, other, preview, keep, onKeepChange }

  return (
    <section className="merge-pair__card" aria-label={label}>
      <header className="merge-pair__card-head">
        <h3 className="merge-pair__card-title">{label}</h3>
        {preview && hasChoices(preview) && (
          <button
            type="button"
            className="merge-pair__use-all"
            onClick={() => onKeepChange(pickAll(keep, preview, row.id))}
            disabled={suppliesAll(preview, row.id)}
          >
            Use all
          </button>
        )}
      </header>

      <div className="merge-pair__row">
        <span className="merge-pair__key">Date</span>
        <Value field="date" name="date" {...pickable}>
          {formatDate(row.date)}
        </Value>
      </div>
      <div className="merge-pair__row">
        <span className="merge-pair__key">Payee</span>
        <Value field="payee" name="payee" {...pickable}>
          {row.payee_id ? (payeeMap.get(row.payee_id) ?? '—') : '—'}
        </Value>
      </div>
      <div className="merge-pair__row">
        <span className="merge-pair__key">Category</span>
        <Value field="category" name="category" {...pickable}>
          <Tooltip content={categoryCellHover(category)} block>
            {categoryCellText(category)}
          </Tooltip>
        </Value>
      </div>
      {row.is_split && lines && (
        <Lines lines={lines} categoryLabels={categoryLabels} formatMoney={formatMoney} />
      )}
      <div className="merge-pair__row">
        <span className="merge-pair__key">Memo</span>
        <Value field="memo" name="memo" {...pickable}>
          {row.memo || '—'}
        </Value>
      </div>
      <div className="merge-pair__row">
        <span className="merge-pair__key">Amount</span>
        <span
          className={`merge-pair__value tabular ${row.amount < 0 ? 'txn-outflow' : 'txn-inflow'}`}
        >
          {signed(row.amount, formatMoney)}
        </span>
      </div>
      <div className="merge-pair__row">
        <span className="merge-pair__key">Status</span>
        <span className="merge-pair__value merge-pair__status">{row.cleared}</span>
      </div>
      {row.import_description && (
        <div className="merge-pair__row">
          <span className="merge-pair__key">Bank desc</span>
          <span className="merge-pair__value merge-pair__muted">{row.import_description}</span>
        </div>
      )}
    </section>
  )
}

const TRANSFER_NOTE: Record<NonNullable<MergePreview['transfer']>, string> = {
  kept: 'It stays one side of its transfer.',
  taken_over: 'It takes over the transfer the other one was part of.',
  other_side_merged:
    'Both are sides of a transfer, so the matching pair in the other account is merged too.',
}

function Result({
  preview,
  payeeMap,
  categoryLabels,
}: {
  preview: MergePreview
  payeeMap: ReadonlyMap<string, string>
  categoryLabels: ReadonlyMap<string, NamedCategory>
}) {
  const { formatMoney, formatDate } = useFormatters()
  const category = preview.category_id ? categoryDisplay(preview.category_id, categoryLabels) : null

  return (
    <section className="merge-pair__result" aria-label="After merging">
      <h3 className="merge-pair__result-title">
        <ArrowDown size={12} aria-hidden />
        After merging: one transaction
      </h3>
      <div className="merge-pair__row">
        <span className="merge-pair__key">Date</span>
        <span className="merge-pair__value">{formatDate(preview.date)}</span>
      </div>
      <div className="merge-pair__row">
        <span className="merge-pair__key">Payee</span>
        <span className="merge-pair__value">
          {preview.payee_id ? (payeeMap.get(preview.payee_id) ?? '—') : '—'}
        </span>
      </div>
      <div className="merge-pair__row">
        <span className="merge-pair__key">Category</span>
        <span className="merge-pair__value">
          {preview.is_split ? (
            `Split, ${preview.lines.length} lines`
          ) : category ? (
            <Tooltip content={category.path} block>
              {category.name}
            </Tooltip>
          ) : (
            '—'
          )}
        </span>
      </div>
      {preview.is_split && (
        <Lines lines={preview.lines} categoryLabels={categoryLabels} formatMoney={formatMoney} />
      )}
      <div className="merge-pair__row">
        <span className="merge-pair__key">Memo</span>
        <span className="merge-pair__value">{preview.memo || '—'}</span>
      </div>
      <div className="merge-pair__row">
        <span className="merge-pair__key">Amount</span>
        <span
          className={`merge-pair__value tabular ${preview.amount < 0 ? 'txn-outflow' : 'txn-inflow'}`}
        >
          {signed(preview.amount, formatMoney)}
        </span>
      </div>
      {preview.replaced_amount !== null && (
        <p className="merge-pair__note">
          The bank posted {formatMoney(Math.abs(preview.amount))}, so it replaces the{' '}
          {formatMoney(Math.abs(preview.replaced_amount))} that was entered.
        </p>
      )}
      <div className="merge-pair__row">
        <span className="merge-pair__key">Status</span>
        <span className="merge-pair__value merge-pair__status">{preview.cleared}</span>
      </div>
      {preview.has_bank_record && (
        <div className="merge-pair__row">
          <span className="merge-pair__key">Bank record</span>
          <span className="merge-pair__value">Kept</span>
        </div>
      )}
      {preview.transfer && <p className="merge-pair__note">{TRANSFER_NOTE[preview.transfer]}</p>}
    </section>
  )
}

/**
 * Two transactions that are about to become one: each as it is now, and the
 * one that will be left.
 *
 * The register's merge dialog showed which row would be kept and nothing of
 * what it would then read — a split's category looked like it was simply
 * dropped — and the duplicate review composed its own result on the client.
 * Both draw this now, and the result is the server's
 * (`useMergePreview`): the same preparation the merge writes from.
 *
 * Where the two rows disagree, the differing values are buttons and the
 * person picks which one the merged transaction reads. Everything else
 * carries over without being asked about.
 */
export function MergePair({
  rows,
  labels,
  preview,
  refusal,
  keep,
  onKeepChange,
  payeeMap,
  categoryLabels,
  accountOnBudget,
}: Props) {
  const [a, b] = rows
  const shared = { preview, keep, onKeepChange, payeeMap, categoryLabels, accountOnBudget }

  return (
    <div className="merge-pair">
      {preview && hasChoices(preview) && (
        <p className="merge-pair__hint">
          These two disagree in places. Pick the value to keep wherever one is outlined; everything
          else carries over.
        </p>
      )}
      <div className="merge-pair__cards">
        <Card row={a} other={b} label={labels[0]} {...shared} />
        <Card row={b} other={a} label={labels[1]} {...shared} />
      </div>

      {refusal ? (
        <p className="merge-pair__refusal" role="alert">
          These can’t be merged: {refusal}
        </p>
      ) : preview ? (
        <Result preview={preview} payeeMap={payeeMap} categoryLabels={categoryLabels} />
      ) : (
        <p className="merge-pair__working" role="status">
          Working out the result…
        </p>
      )}
    </div>
  )
}
