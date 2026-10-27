import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../test-utils/cssRules'

/**
 * Controls the 2026-09-08 audit measured under 44px on a phone, pinned to
 * the tap floor as source. jsdom has no layout, so the pixels themselves are
 * measured in headless Chrome; what a test can hold is that each of these
 * declares `--tap-min` in a phone or touch context.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

const CASES: Array<[file: string, selector: string, prop: string]> = [
  ['pages/PayeesPage/PayeesPage.css', '.payees-search', 'min-height'],
  ['pages/PayeesPage/PayeesPage.css', '.payees-btn', 'min-height'],
  // The phone's account header: one row, and the two sheets behind it. The
  // desktop header (its fold control, its action buttons, the duplicates
  // banner) is not drawn on a phone, so it owes the floor nowhere.
  ['pages/AccountPage/AccountPhoneHeader.css', '.account-phone-header__notice', 'min-height'],
  ['pages/AccountPage/AccountPhoneHeader.css', '.account-phone-header__notice', 'min-width'],
  ['pages/AccountPage/AccountPhoneHeader.css', '.account-phone-header__primary', 'min-height'],
  ['pages/AccountPage/AccountPhoneHeader.css', '.account-phone-header__tools', 'min-height'],
  ['pages/AccountPage/AccountPhoneHeader.css', '.account-phone-header__tools', 'min-width'],
  ['pages/AccountPage/AccountSheets.css', '.account-sheet__action', 'min-height'],
  ['pages/AccountPage/AccountSheets.css', '.account-sheet__notice-btn', 'min-height'],
  [
    'pages/AccountPage/AccountSheets.css',
    '.account-sheet .account-page__pill-button',
    'min-height',
  ],
  ['pages/AccountPage/AccountSheets.css', '.account-sheet .liability-terms__btn', 'min-height'],
  ['pages/AccountPage/AccountSheets.css', '.account-sheet .liability-terms__link', 'min-height'],
  ['components/accounts/PendingReviewBanner.css', '.pending-review-banner__btn', 'min-height'],
  // Every section fold — on a phone the register's Upcoming starts folded.
  ['components/common/Collapsible/Collapsible.css', '.collapsible__header', 'min-height'],
  ['pages/GuidePage/GuidePage.css', '.guide-nav__tab', 'min-height'],
  ['pages/ReportsPage/ReportsPage.css', '.reports-nav__tab', 'min-height'],
  ['pages/BudgetSelectorPage/BudgetSelectorPage.css', '.ynab-mapping__disposition', 'min-height'],
  ['pages/BudgetSelectorPage/BudgetSelectorPage.css', '.ynab-mapping__type', 'min-height'],
  [
    'components/budget/BudgetViewModal/BudgetViewModal.css',
    '.view-editor__chip-move',
    'min-height',
  ],
  // The phone's budget header (M2): one row, and the Tools sheet behind it.
  ['components/budget/TbaHero/TbaHero.css', '.tba-hero__tools-btn', 'min-height'],
  ['components/budget/TbaHero/TbaHero.css', '.tba-hero__tools-btn', 'min-width'],
  ['components/budget/BudgetFilterBar/BudgetToolsSheet.css', '.budget-tools__row', 'min-height'],
  ['components/budget/BudgetFilterBar/BudgetToolsSheet.css', '.budget-tools__link', 'min-height'],
  [
    'components/budget/BudgetFilterBar/BudgetToolsSheet.css',
    '.budget-tools__density button',
    'min-height',
  ],
  [
    'components/budget/BudgetFilterBar/BudgetFilterStrip.css',
    '.budget-filter-strip__chip',
    'min-height',
  ],
]

const isTouch = (atRules: string[]) =>
  atRules.some((a) => /\(hover:\s*none\)/.test(a) || /\(max-width:\s*768px\)/.test(a))

describe('phone tap targets', () => {
  it.each(CASES)('%s %s declares %s: var(--tap-min) for touch', (file, selector, prop) => {
    const rules = rulesWithContext(stripComments(readFileSync(join(SRC, file), 'utf8')))
    const hit = rules.find(
      (r) =>
        r.selector.split(',').some((s) => s.trim() === selector) &&
        isTouch(r.atRules) &&
        new RegExp(`${prop}\\s*:\\s*var\\(--tap-min\\)`).test(r.body)
    )
    expect(hit, `${selector} in a touch context`).toBeDefined()
  })
})

describe('banners wrap on phones instead of pushing their buttons off the edge', () => {
  // The account page's duplicates banner is not drawn on a phone any more —
  // its notice lives behind the header's pill (AccountNoticesSheet).
  it.each([['components/accounts/PendingReviewBanner.css', '.pending-review-banner']])(
    '%s %s',
    (file, selector) => {
      const rules = rulesWithContext(stripComments(readFileSync(join(SRC, file), 'utf8')))
      const hit = rules.find(
        (r) =>
          r.selector.trim() === selector && isTouch(r.atRules) && /flex-wrap:\s*wrap/.test(r.body)
      )
      expect(hit).toBeDefined()
    }
  )
})

describe('the YNAB mapping row restacks on phones', () => {
  it('puts the account name on its own line', () => {
    const rules = rulesWithContext(
      stripComments(
        readFileSync(join(SRC, 'pages/BudgetSelectorPage/BudgetSelectorPage.css'), 'utf8')
      )
    )
    const row = rules.find((r) => r.selector.trim() === '.ynab-mapping__row' && isTouch(r.atRules))
    expect(row?.body).toMatch(
      /grid-template-areas:\s*"name name"\s*"disposition type"\s*"toggle toggle"/
    )
  })
})
