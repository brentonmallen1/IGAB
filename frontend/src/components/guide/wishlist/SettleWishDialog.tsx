import { useMemo, useState } from 'react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { apiErrorMessage } from '../../../api/client'
import { useSettleWish, type Wish } from '../../../api/wishlist'
import { groupedCategorySections } from '../../../utils/categoryPickers'
import { useFormatters } from '../../../hooks/useFormatters'
import { CategoryCombobox } from '../../common/CategoryCombobox/CategoryCombobox'
import { GuideDialog } from '../GuideDialog'

const TBA = '__tba__'

interface Props {
  budgetId: string
  wish: Wish
  onClose: () => void
}

/**
 * The step that used to be missing.
 *
 * Ending a wish was a status flip: its envelope stayed on the budget page
 * holding money, still carrying a savings goal for something already decided
 * against. This asks the one question the app cannot answer for anyone —
 * where the money goes — and the server does the rest in a single change
 * batch, so ⌘Z puts the money, the goal and the envelope back together.
 *
 * Nothing here re-derives money. `settlement.available` is the budget page's
 * figure, served with the wish; the sign is the server's to act on, and this
 * only says which way it reads.
 */
export function SettleWishDialog({ budgetId, wish, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const settlement = wish.settlement
  const [destination, setDestination] = useState<string>(TBA)
  const [error, setError] = useState<string | null>(null)
  const settle = useSettleWish(budgetId)
  const { data: categories } = useCategories(budgetId)
  const { data: groups } = useCategoryGroups(budgetId)

  // `is_assignable`, like every other envelope picker here: the question is
  // what money may be budgeted into, not what a transaction may be filed to.
  // The envelope being settled is never somewhere its own money can go.
  const sections = useMemo(
    () =>
      groupedCategorySections(
        (categories ?? []).filter((c) => c.is_assignable && c.id !== settlement?.category_id),
        groups ?? []
      ),
    [categories, groups, settlement?.category_id]
  )

  if (!settlement) return null

  const available = settlement.available
  const overspent = available < 0
  const empty = available === 0
  const ended = wish.status === 'done' ? 'bought' : 'dropped'

  async function run(keep_envelope: boolean) {
    setError(null)
    try {
      await settle.mutateAsync({
        id: wish.id,
        destination_category_id: destination === TBA ? null : destination,
        keep_envelope,
      })
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not settle the envelope'))
    }
  }

  return (
    <GuideDialog
      title={empty ? 'Close out the envelope?' : 'Where should this money go?'}
      onClose={onClose}
      historyKey="wishlist-settle"
      footer={
        <div className="dialog-actions">
          {error && (
            <span className="dialog-form__error" role="alert">
              {error}
            </span>
          )}
          <div className="dialog-actions__end">
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={() => void run(true)}
              disabled={settle.isPending}
            >
              Keep the envelope
            </button>
            <button
              type="button"
              className="dialog-btn dialog-btn--primary"
              onClick={() => void run(false)}
              disabled={settle.isPending}
            >
              {settle.isPending ? 'Settling…' : empty ? 'Archive it' : 'Move and archive'}
            </button>
          </div>
        </div>
      }
    >
      <div className="dialog__body wish-settle">
        <p className="wish-settle__lede">
          <strong>{wish.name}</strong> is {ended}, but its envelope{' '}
          <strong>{settlement.name}</strong>{' '}
          {empty ? (
            <>is still on your budget, still asking for the wish&rsquo;s cost.</>
          ) : overspent ? (
            <>
              is <strong>{formatMoney(Math.abs(available))} overspent</strong>.
            </>
          ) : (
            <>
              still holds <strong>{formatMoney(available)}</strong>.
            </>
          )}
        </p>

        {!empty && (
          <div className="tool__field">
            <span>{overspent ? 'Cover it from' : 'Move it to'}</span>
            <CategoryCombobox
              value={destination}
              onChange={(id) => setDestination(id ?? TBA)}
              groups={sections}
              topOptions={[{ id: TBA, label: 'Ready to Assign' }]}
              sheetTitle={overspent ? 'Cover from' : 'Move to'}
              aria-label={overspent ? 'Cover from' : 'Move to'}
            />
          </div>
        )}

        <p className="wish-settle__note">
          {settlement.has_goal && <>The savings goal goes with the wish. </>}
          Archiving keeps the envelope&rsquo;s history in your reports and takes it off the budget
          page. Keep it instead to re-purpose it for something else. Money assigned to a later month
          stays where it is — the server will say so rather than archive it out of sight.
        </p>
      </div>
    </GuideDialog>
  )
}
