/**
 * What the "Edit months before the import" switch should send, decided apart
 * from the page that sends it — the `wishlistToggle` pattern: the IO is
 * injected, so each branch is a one-line test.
 *
 * Both directions ask first. Turning it on trades away the match with YNAB
 * the import was built to give; turning it off sets aside every edit made to
 * the earlier months while it was on. Neither is a thing to do by accident.
 *
 * The import preview asks the same question with the same words when someone
 * picks "Work out every month" there, by calling this with `editable: true` —
 * one warning, wherever the choice is made.
 */
import type { HistoryMode } from '../api/budgets'

export interface HistoryModeToggleDeps {
  confirm: (message: { title: string; message: string; confirmLabel: string }) => Promise<boolean>
  /** "October 2026" — the import month, in the words the dialog uses. */
  importMonth: string
  /** Earlier months can already be viewed read-only (`BudgetHistory.keeps_history`)
   *  — the first thing to say to someone who only wants to look back. */
  keepsHistory: boolean
}

/** The mode to PUT, or null to do nothing. `editable` is the switch's new
 *  position: on = re-derived history. */
export async function historyModeToggleOutcome(
  editable: boolean,
  deps: HistoryModeToggleDeps
): Promise<HistoryMode | null> {
  const month = deps.importMonth
  const ok = editable
    ? await deps.confirm({
        title: 'Edit months before your import?',
        message:
          `Only do this if you need to change months before ${month}` +
          (deps.keepsHistory
            ? ' — you can already look back at them, read-only, as YNAB showed them. '
            : '. ') +
          `IGAB will work out every month from your first transaction, under its own rules. ` +
          "Your envelopes, card reserves and Ready to Assign will stop matching YNAB, and card reserves can drift. On a budget set this way, those differences are expected — they aren't bugs. " +
          `You can switch back: ${month} onward returns to YNAB's figures, and edits to earlier months stop counting.`,
        confirmLabel: 'Edit earlier months',
      })
    : await deps.confirm({
        title: "Start from YNAB's figures again?",
        message:
          `Envelopes and card reserves will start in ${month} from YNAB's figures again, as they did after the import. ` +
          `Anything you changed in the months before ${month} stays in the register but no longer counts toward any envelope.`,
        confirmLabel: "Use YNAB's figures",
      })
  if (!ok) return null
  return editable ? 'rederived' : 'anchored'
}
