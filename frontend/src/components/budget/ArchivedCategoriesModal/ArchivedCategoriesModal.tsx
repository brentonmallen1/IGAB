import { Archive, RotateCcw, Trash2 } from 'lucide-react'
import { Modal } from '../../common/Modal/Modal'
import {
  useArchivedCategories,
  useUnarchiveCategories,
  type ArchivedCategory,
  type DeleteTarget,
} from '../../../api/categories'
import { useFormatters } from '../../../hooks/useFormatters'
import { parseApiDecimal } from '../../../utils/money'
import './ArchivedCategoriesModal.css'

interface Props {
  budgetId: string
  /** The month on screen. A balance left in an archived envelope is a
   *  month-dependent figure, so it is quoted for the month the user is
   *  looking at — the rule the delete dialog already follows. */
  month: string
  onClose: () => void
  onDelete: (target: DeleteTarget) => void
}

/**
 * Where archived envelopes live, now that they are not in the grid at all.
 *
 * The old arrangement drew them greyed out behind a "Show hidden" toggle: in
 * the budget but unusable, which is the worst of both states and left nobody
 * able to say what the flag meant. They get their own room instead, with the
 * three things that decide an envelope's fate — how much history it carries,
 * when it was put away, and whether anything is still in it.
 *
 * Nothing here re-derives money. Every figure comes from the server's archived
 * listing, the same rule `DeleteCategoryModal` states for the delete preview.
 */
export function ArchivedCategoriesModal({ budgetId, month, onClose, onDelete }: Props) {
  const { formatMoney } = useFormatters()
  const { data: rows = [], isLoading } = useArchivedCategories(budgetId, month)
  const unarchive = useUnarchiveCategories(budgetId)

  const stranded = rows.filter((r) => parseApiDecimal(r.available) !== 0)

  return (
    <Modal onClose={onClose} className="archived-modal__overlay" historyKey="archived-categories">
      <div className="archived-modal">
        <h2 className="archived-modal__title">
          <Archive size={16} /> Archived envelopes
        </h2>
        <p className="archived-modal__lede">
          Out of the budget, but nothing is lost — their spending still counts in every report.
          Restore one to use it again, or delete it to decide what becomes of its transactions.
        </p>

        {stranded.length > 0 && (
          // These predate the archive flow, which now refuses to leave money
          // behind. The budget page no longer draws them, so this banner is
          // the only place that money is mentioned at all.
          <p className="archived-modal__warning">
            {stranded.length === 1
              ? `${stranded[0].name} still holds money.`
              : `${stranded.length} of these still hold money.`}{' '}
            Restore to move it somewhere you can see it.
          </p>
        )}

        {isLoading ? (
          <p className="archived-modal__empty">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="archived-modal__empty">
            Nothing archived. Envelopes you archive from the budget will appear here.
          </p>
        ) : (
          <ul className="archived-modal__list">
            {rows.map((row) => (
              <Row
                key={row.id}
                row={row}
                formatMoney={formatMoney}
                onRestore={() => unarchive.mutate({ ids: [row.id], month })}
                onDelete={() => onDelete({ kind: 'categories', ids: [row.id], name: row.name })}
              />
            ))}
          </ul>
        )}
      </div>
    </Modal>
  )
}

function Row({
  row,
  formatMoney,
  onRestore,
  onDelete,
}: {
  row: ArchivedCategory
  formatMoney: (n: number) => string
  onRestore: () => void
  onDelete: () => void
}) {
  const available = parseApiDecimal(row.available)
  return (
    <li className="archived-modal__row">
      <div className="archived-modal__identity">
        <span className="archived-modal__name">{row.name}</span>
        <span className="archived-modal__group">{row.group_name}</span>
      </div>
      <div className="archived-modal__facts">
        <span>
          {row.transaction_count === 1
            ? '1 transaction'
            : `${row.transaction_count.toLocaleString()} transactions`}
        </span>
        <span>{archivedOn(row.archived_at)}</span>
        {available !== 0 && (
          <span className="archived-modal__balance">{formatMoney(available)} left in it</span>
        )}
      </div>
      <div className="archived-modal__actions">
        <button type="button" className="archived-modal__btn" onClick={onRestore}>
          <RotateCcw size={12} /> Restore
        </button>
        <button
          type="button"
          className="archived-modal__btn archived-modal__btn--danger"
          onClick={onDelete}
        >
          <Trash2 size={12} /> Delete
        </button>
      </div>
    </li>
  )
}

/** Rows archived before the column existed carry no date. Saying so beats
 *  inventing one from `updated_at`, which any edit would have bumped. */
function archivedOn(value: string | null): string {
  if (!value) return 'Archived before dates were kept'
  return `Archived ${new Date(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })}`
}
