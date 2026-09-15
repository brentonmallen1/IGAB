/**
 * What catches people out about setting money aside. Prose only: the claims
 * are the ones the examples above this list show with served figures.
 */
import { savingsModeLabel } from '../../../utils/savingsModes'
import type { CatchOutItem } from '../CatchOuts'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'

const SAVINGS = systemTagName('savings')
const SINKING = systemTagName('long_term_expense')
const FUND = systemTagName('emergency_fund')
const SENT = savingsModeLabel('sent_out')
const KEPT = savingsModeLabel('kept_here')

export const ASIDE_CATCH_OUTS: CatchOutItem[] = [
  {
    id: 'sent-out-repair',
    title: `An envelope that counts as saved ${SENT} counts a repair as saved`,
    detail: `A ${SAVINGS} envelope that counts as saved ${SENT} counts a repair paid from it, since that money left the budget. For a fund you spend from, set it to count as saved ${KEPT}: spending from it is then spending.`,
  },
  {
    id: 'savings-and-sinking',
    title: `${SAVINGS} plus ${SINKING} is savings, not a sinking fund`,
    detail: `A category with both tags counts as savings and leaves the Sinking funds list. Its inspector warns you; pick the one it really is.`,
  },
  {
    id: 'marked-account-counts-as-savings',
    title: 'A marked account must also count as savings',
    detail: `An off-budget account that counts toward the emergency fund has to count as savings too, or money moved into it would read as spending. The checklist turns it on when you mark the account.`,
  },
  {
    id: 'on-budget-account',
    title: 'An on-budget account can’t be marked',
    detail: `Its money is already in your envelopes, and they say what each dollar is for. Tag the envelopes that hold emergency money ${FUND} instead.`,
  },
  {
    id: 'young-budget',
    title: 'A young budget under-reads spread bills',
    detail: `Spread counts a twelfth of each ${SINKING} bill from the last year. Until the budget has seen a yearly bill once, that twelfth is missing, so essentials read low.`,
  },
  {
    id: 'dont-track',
    title: 'Choosing “Don’t track this in the Guide” doesn’t hide the fund from reports',
    detail:
      'It stops the Guide asking about your emergency fund. The Emergency Fund and Essentials reports still show what you chose.',
  },
]
