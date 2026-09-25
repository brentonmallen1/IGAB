import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronRight, X } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  useLinkCardPayments,
  useRepairTrackingCategories,
  useRepairTransfers,
  type FindingItem,
  type HygieneFinding,
} from '../../api/accounts'
import { apiErrorMessage } from '../../api/client'
import { useFormatters } from '../../hooks/useFormatters'
import { confirmAsync } from '../../stores/confirmStore'
import { parseApiDecimal } from '../../utils/money'
import './HygieneFindings.css'

/** Past this many, a finding's list folds behind "Show N more" — the panel
 *  is read top to bottom, and nine rows of one finding push the next out. */
const ITEMS_SHOWN = 5

/**
 * Findings about a budget's accounts, and what to do about each.
 *
 * One renderer for one server rule. The findings are computed by
 * `AccountHygieneService`, and they appear in two places — the accounts page,
 * where they persist, and the import review, where they are most actionable —
 * so a second copy of this markup would be a second copy of what each finding
 * means.
 *
 * `onDismiss` is the accounts page's alone: dismissal is a standing decision
 * to live with something, which is not a thing to offer inside a one-off
 * review. Given no handler, no dismiss control is drawn.
 *
 * Each finding reads in a fixed order — what is wrong, which things, what to
 * do, and (folded) why. They used to be two paragraphs of server prose with
 * the figures typed into them, and the action was a sentence to be found.
 */
export function HygieneFindings({
  findings,
  budgetId,
  onDismiss,
  onNavigate,
}: {
  findings: HygieneFinding[]
  budgetId: string
  onDismiss?: (kind: string) => void
  /** Fired before routing away — a dialog uses it to close itself first. */
  onNavigate?: () => void
}) {
  const navigate = useNavigate()
  const repair = useRepairTransfers(budgetId)
  const stripCategories = useRepairTrackingCategories(budgetId)
  const linkPayments = useLinkCardPayments(budgetId)

  async function linkCardPayments(f: HygieneFinding) {
    const n = f.items.length
    const ok = await confirmAsync({
      title: `Link ${n} card payment${n === 1 ? '' : 's'}?`,
      message:
        'Each becomes a transfer to its card. Where the payment was filed to an ' +
        'envelope, that envelope gets the money back and the card’s Set aside falls by ' +
        'the same amount — move it to the card afterwards. Undo reverses all of them.',
      confirmLabel: 'Link them',
    })
    if (!ok) return
    try {
      const r = await linkPayments.mutateAsync(f.items.map((i) => i.transaction_ids))
      const skipped = r.skipped ? ` ${r.skipped} had changed and were left alone.` : ''
      toast.success(`Linked ${r.linked} payment${r.linked === 1 ? '' : 's'}.${skipped}`, {
        duration: 8000,
      })
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not link the payments'))
    }
  }

  async function repairTrackingCategories() {
    try {
      const r = await stripCategories.mutateAsync()
      toast.success(
        r.stripped
          ? `Removed the category from ${r.stripped} transaction${r.stripped === 1 ? '' : 's'} — undo restores them.`
          : 'Nothing to remove — the budget is already clean.',
        { duration: 8000 }
      )
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not remove the categories'))
    }
  }

  async function repairTransfers() {
    try {
      const r = await repair.mutateAsync()
      // Say what is left as well as what was fixed: a pass that links 900 of
      // 1,117 and says only "900 linked" reads as finished.
      const left = [
        r.ambiguous ? `${r.ambiguous} need you to choose` : '',
        r.remaining ? `${r.remaining} have no other side` : '',
      ].filter(Boolean)
      const summary = r.linked
        ? `Linked ${r.linked} transfer${r.linked === 1 ? '' : 's'}`
        : 'Nothing could be linked automatically'
      toast.success(left.length ? `${summary} — ${left.join(', ')}.` : `${summary}.`, {
        duration: 8000,
      })
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not repair the transfers'))
    }
  }

  // Where a finding leads as a whole. Most lead through their items now —
  // each card, envelope or row links to its own register — so this is only
  // for findings whose items cannot: a count with no rows listed, an asset,
  // or the card diagnostics whose months live on the budget page.
  function target(f: HygieneFinding): { to: string; label: string } | null {
    if (f.kind === 'unpaired_transfer_legs') {
      return { to: '/transactions?q=is:unpaired', label: 'Show them' }
    }
    // Asset findings lead to the asset — where the value can be restated,
    // or the double-counted thing deleted.
    if (
      (f.kind === 'stale_asset_value' || f.kind === 'asset_beside_asset_account') &&
      f.asset_ids.length > 0
    ) {
      return { to: `/assets/${f.asset_ids[0]}`, label: 'Show them' }
    }
    // The card diagnostics resolve on the budget page's cards section — the
    // Set aside breakdown is where the months and legs they cite live.
    if (
      f.kind === 'card_debt_predates_budget' ||
      f.kind === 'residual_on_uncharged_category' ||
      f.kind === 'recurring_card_residual'
    ) {
      return { to: '/budget', label: 'Open the budget' }
    }
    return null
  }

  function go(to: string) {
    onNavigate?.()
    navigate(to)
  }

  return (
    <div className="hygiene__list">
      {findings.map((f) => {
        const t = target(f)
        return (
          <div key={f.kind} className="hygiene__item">
            <AlertTriangle className="hygiene__icon" size={15} aria-hidden />
            <div className="hygiene__body">
              <div className="hygiene__title">{f.title}</div>
              <p className="hygiene__summary">{f.summary}</p>
              {f.items.length > 0 && <FindingItems items={f.items} onGo={go} />}
              <p className="hygiene__action">
                <span className="hygiene__action-label">What to do</span> {f.action}
                {f.kind === 'unlinked_card_payments' && f.items.length > 0 && (
                  <button
                    type="button"
                    className="hygiene__link"
                    onClick={() => linkCardPayments(f)}
                    disabled={linkPayments.isPending}
                  >
                    {linkPayments.isPending ? 'Linking…' : `Link all ${f.items.length}`}
                    <ChevronRight size={12} />
                  </button>
                )}
                {f.kind === 'categorized_tracking_rows' && (
                  <button
                    type="button"
                    className="hygiene__link"
                    onClick={repairTrackingCategories}
                    disabled={stripCategories.isPending}
                  >
                    {stripCategories.isPending ? 'Removing…' : 'Remove the categories'}
                    <ChevronRight size={12} />
                  </button>
                )}
                {f.kind === 'unpaired_transfer_legs' && (
                  <button
                    type="button"
                    className="hygiene__link"
                    onClick={repairTransfers}
                    disabled={repair.isPending}
                  >
                    {repair.isPending ? 'Matching…' : 'Match them up'}
                    <ChevronRight size={12} />
                  </button>
                )}
                {t && (
                  <button type="button" className="hygiene__link" onClick={() => go(t.to)}>
                    {t.label} <ChevronRight size={12} />
                  </button>
                )}
              </p>
              {f.why && (
                <details className="hygiene__why">
                  <summary>Why</summary>
                  <p>{f.why}</p>
                </details>
              )}
            </div>
            {onDismiss && (
              <button
                type="button"
                className="hygiene__dismiss"
                onClick={() => onDismiss(f.kind)}
                aria-label={`Dismiss: ${f.title}`}
                title="Dismiss — this kind of suggestion won't come back"
              >
                <X size={14} />
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** Where an item leads: the row itself when it names one, else its account. */
export function itemTarget(item: FindingItem): string | null {
  if (!item.account_id) return null
  const base = `/accounts/${item.account_id}`
  return item.transaction_id ? `${base}?highlight=${item.transaction_id}` : base
}

function FindingItems({ items, onGo }: { items: FindingItem[]; onGo: (to: string) => void }) {
  const { formatMoney, formatDate, formatMonth } = useFormatters()
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? items : items.slice(0, ITEMS_SHOWN)
  const hidden = items.length - shown.length

  return (
    <ul className="hygiene__items">
      {shown.map((item, i) => {
        const to = itemTarget(item)
        const when = item.day
          ? formatDate(item.day)
          : item.month
            ? `since ${formatMonth(item.month)}`
            : null
        return (
          <li key={`${item.label}-${i}`} className="hygiene__row">
            <span className="hygiene__row-main">
              {to ? (
                <button type="button" className="hygiene__row-label" onClick={() => onGo(to)}>
                  {item.label}
                </button>
              ) : (
                <span className="hygiene__row-label">{item.label}</span>
              )}
              {item.note && <span className="hygiene__row-note">{item.note}</span>}
              {when && <span className="hygiene__row-note">{when}</span>}
            </span>
            {item.amount !== null && (
              <span className="hygiene__row-amount">
                {formatMoney(parseApiDecimal(item.amount))}
              </span>
            )}
          </li>
        )
      })}
      {hidden > 0 && (
        <li>
          <button type="button" className="hygiene__link" onClick={() => setExpanded(true)}>
            Show {hidden} more
          </button>
        </li>
      )}
    </ul>
  )
}
