/**
 * What the mapping screen says about the account list before you read it.
 *
 * Four notes, each guarded by a question about the preview rather than a
 * proxy for one — the "IGAB export" note used to ask "did nothing need
 * review?", which is also true of a plain YNAB export whose names all read
 * confidently, and then claimed the file carried real types it did not have.
 *
 * Extracted from the page because the page is already past its length budget
 * and these are pure presentation of server-supplied facts plus two actions.
 */
import { allTypesFromExport, rememberedCount } from './accountMapping'
import type { YnabAccountPreview } from '../../api/budgets'

interface Props {
  accounts: YnabAccountPreview[]
  dormantCount: number
  forgetPending: boolean
  onForgetRemembered: () => void
  onCloseDormant: () => void
}

export function MappingNotes({
  accounts,
  dormantCount,
  forgetPending,
  onForgetRemembered,
  onCloseDormant,
}: Props) {
  const reviewCount = accounts.filter((a) => a.needs_review).length
  const remembered = rememberedCount(accounts)
  return (
    <>
      {allTypesFromExport(accounts) && (
        <p className="ynab-mapping__note">
          An IGAB export carries the real account types, so there is nothing to guess here. A YNAB
          export does not, and the types below would be read from account names instead.
        </p>
      )}
      {reviewCount > 0 && (
        <p className="ynab-mapping__review-note">
          We couldn&apos;t tell what {reviewCount} of these are from their names — they&apos;re
          marked <strong>Check</strong> below. The balance is the clue: a large one usually means
          something you own (a house, a car, a brokerage), which belongs <em>off</em> budget. An
          account left on budget by mistake throws off every total.
        </p>
      )}
      {remembered > 0 && (
        <p className="ynab-mapping__note">
          {remembered} of these are set the way you left them last time — marked{' '}
          <strong>Remembered</strong> below.{' '}
          <button
            type="button"
            className="ynab-mapping__note-action"
            disabled={forgetPending}
            onClick={onForgetRemembered}
          >
            Forget them
          </button>{' '}
          to start from scratch. Anything still marked <strong>Check</strong> is a name we
          couldn&apos;t read then either.
        </p>
      )}
      {dormantCount > 0 && (
        <p className="ynab-mapping__note">
          {dormantCount} of these {dormantCount === 1 ? 'has' : 'have'} seen no activity in over a
          year.{' '}
          <button type="button" className="ynab-mapping__note-action" onClick={onCloseDormant}>
            Import &amp; close {dormantCount === 1 ? 'it' : 'them'}
          </button>{' '}
          to keep every transaction while leaving them out of your account pickers.
        </p>
      )}
    </>
  )
}
