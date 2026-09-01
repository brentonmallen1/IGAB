import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronRight, X } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  useRepairTrackingCategories,
  useRepairTransfers,
  type HygieneFinding,
} from '../../api/accounts'
import { apiErrorMessage } from '../../api/client'
import './HygieneFindings.css'

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

  // The two that lead somewhere other than the accounts list itself. A
  // finding with no next step is criticism, per the service that raises them.
  function target(f: HygieneFinding): string | null {
    if (f.kind === 'unpaired_transfer_legs') return '/transactions?q=is:unpaired'
    // The card's own register, where the credits sit and can be linked to
    // their partner. `account_ids` leads with the card for exactly this.
    if (f.kind === 'unlinked_card_payments' && f.account_ids.length > 0) {
      return `/accounts/${f.account_ids[0]}`
    }
    // The card diagnostics all resolve on the budget page's cards section —
    // the Ready to pay breakdown is where the months and legs they cite live.
    if (
      f.kind === 'card_reserve_went_negative' ||
      f.kind === 'card_debt_predates_budget' ||
      f.kind === 'residual_on_uncharged_category' ||
      f.kind === 'card_inflow_belongs_to_other_card' ||
      f.kind === 'payment_envelope_shadow'
    ) {
      return '/budget'
    }
    return null
  }

  function go(to: string) {
    onNavigate?.()
    navigate(to)
  }

  return (
    <div className="hygiene__list">
      {findings.map((f) => (
        <div key={f.kind} className="hygiene__item">
          <AlertTriangle className="hygiene__icon" size={15} aria-hidden />
          <div className="hygiene__body">
            <div className="hygiene__title">{f.title}</div>
            <p className="hygiene__detail">{f.detail}</p>
            <p className="hygiene__action">
              {f.action}
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
              {target(f) && (
                <button
                  type="button"
                  className="hygiene__link"
                  onClick={() => go(target(f) as string)}
                >
                  Show them <ChevronRight size={12} />
                </button>
              )}
            </p>
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
      ))}
    </div>
  )
}
