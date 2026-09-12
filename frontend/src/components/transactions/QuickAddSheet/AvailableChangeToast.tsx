import { useFormatters } from '../../../hooks/useFormatters'
import { availableTone } from '../../../utils/categoryBalances'
import { CountUpMoney } from '../../common/CountUpMoney/CountUpMoney'
import type { CategoryBalance } from '../../../types'
import './AvailableChangeToast.css'

interface Props {
  /** The toast's usual sentence, "Added −$42.00". */
  headline: string
  categoryName: string
  /** Available as the sheet had it loaded when Save was pressed. */
  before: number
  /** The server's balance once the save landed. */
  after: CategoryBalance & { available: number }
}

/**
 * What a quick-add save did to its envelope: "Groceries $240.00 → $198.00",
 * the new figure counting down from the old.
 *
 * Coloured only where the grid would colour it: red for an overspend, the
 * grid's calm secondary for red that rides on a card (`availableTone`, the
 * same reading CategoryRow uses). A positive result stays plain — the toast
 * is a receipt, not a celebration.
 */
export function AvailableChangeToast({ headline, categoryName, before, after }: Props) {
  const { formatMoney } = useFormatters()
  const tone = availableTone(after)
  return (
    <span className="available-change-toast">
      <span>{headline}</span>
      <span className="available-change-toast__line">
        <span className="available-change-toast__category">{categoryName}</span>
        <span className="available-change-toast__figures">
          {formatMoney(before)}
          <span aria-hidden="true"> → </span>
          <span className="sr-only"> to </span>
          <CountUpMoney
            from={before}
            to={after.available}
            className={`available-change-toast__after available-change-toast__after--${tone}`}
          />
        </span>
      </span>
    </span>
  )
}
