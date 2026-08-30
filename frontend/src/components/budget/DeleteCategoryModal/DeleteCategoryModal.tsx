import { useMemo, useState } from 'react'
import { AlertTriangle, Lock } from 'lucide-react'
import { Modal } from '../../common/Modal/Modal'
import { CategoryCombobox } from '../../common/CategoryCombobox/CategoryCombobox'
import {
  useCategories,
  useArchiveCategories,
  useArchivePreview,
  useCategoryDeletePreview,
  useCategoryGroups,
  useDeleteCategories,
  type DeleteTarget,
} from '../../../api/categories'
import { useFormatters } from '../../../hooks/useFormatters'
import { parseApiDecimal } from '../../../utils/money'
import './DeleteCategoryModal.css'

interface Props {
  budgetId: string
  target: DeleteTarget
  /** The month on screen. Ready to Assign is month-dependent, so the figures
   *  quoted here are the ones the user is currently looking at. */
  month: string
  onClose: () => void
  onDeleted: (changeId: string) => void
}

/**
 * The one place a category delete is confirmed.
 *
 * This replaced three copies of a one-line `confirmAsync` that all said
 * "Transactions will lose their category" — a sentence that was not true. The
 * old delete flipped a flag and left every transaction pointing at the dead
 * category. Now it is true, which is exactly why the dialog has to say what
 * *else* moves: money returns to Ready to Assign, and this category's spending
 * leaves the reports that group by category.
 *
 * Nothing here re-derives money. Every figure comes from the server's
 * delete-preview, which a differential test holds to what the delete then
 * does — a confirmation that misreports money is worse than none.
 */
export function DeleteCategoryModal({ budgetId, target, month, onClose, onDeleted }: Props) {
  const [moveTo, setMoveTo] = useState<string | null>(null)
  const [mode, setMode] = useState<'move' | 'uncategorize'>('move')
  const { formatMoney } = useFormatters()

  const { data: preview, isLoading, isError, refetch } = useCategoryDeletePreview(
    budgetId,
    target,
    month
  )
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const deleteCategories = useDeleteCategories(budgetId)
  const archiveCategories = useArchiveCategories(budgetId)

  const doomed = useMemo(() => new Set(preview?.category_ids ?? []), [preview?.category_ids])

  // Only somewhere a transaction may actually be filed, and never one of the
  // categories about to go. `is_categorizable` is the server's rule (a
  // credit-card payment or debt category is maintained by its transfer or its
  // loan, not by filing rows into it); the client only honours it.
  const destinations = useMemo(
    () =>
      groups
        .map((g) => ({
          group: { id: g.id, name: g.name },
          cats: categories
            .filter((c) => c.category_group_id === g.id && c.is_categorizable && !doomed.has(c.id))
            .map((c) => ({ id: c.id, name: c.name })),
        }))
        .filter((g) => g.cats.length > 0),
    [groups, categories, doomed]
  )

  // Whether an *archive* may proceed is a different question from whether a
  // delete may, and the delete preview cannot answer it: `blocked_by` covers
  // links only, where archiving is also refused over a balance, a future
  // assignment or a live schedule. Asking the archive endpoint is what keeps
  // this button and that endpoint from disagreeing — `may_archive` is served
  // precisely so it is never recomputed here.
  const archive = useArchivePreview(budgetId, preview?.category_ids ?? [], month)
  const mayArchive = archive.data?.may_archive ?? false
  //: Which envelope stopped it, straight from the served lists — presentation
  //: of a decision the server already made, not a second copy of the rule.
  const archiveBlockedBy =
    archive.data && !archive.data.may_archive
      ? (archive.data.blocked_by_link[0] ??
        archive.data.blocked_by_balance[0] ??
        archive.data.blocked_by_schedule[0] ??
        null)
      : null

  const blocked = (preview?.blocked_by.length ?? 0) > 0
  const txnCount = preview?.transaction_count ?? 0
  // Only when there is actually something to move. The choice is hidden with
  // no transactions, and gating on a picker nobody can see left the Delete
  // button permanently inert on an empty category.
  const needsDestination = txnCount > 0 && mode === 'move' && !moveTo
  // Served, per mode — never derived here. The two figures differ exactly
  // when future-dated activity moves (its cover is a future assignment the
  // viewed month's Ready to Assign already counts).
  const returning = preview
    ? parseApiDecimal(
        mode === 'move' ? preview.released_if_moved : preview.released_if_uncategorized
      )
    : 0
  const movingActivity = preview ? parseApiDecimal(preview.moving_activity) : 0

  async function handleArchive() {
    if (!preview) return
    // Archiving a group means archiving what is in it, which is what the
    // preview already resolved the target to.
    await archiveCategories.mutateAsync({ ids: preview.category_ids, month })
    onClose()
  }

  async function handleDelete() {
    if (!preview) return
    const result = await deleteCategories.mutateAsync({
      target,
      moveTo: mode === 'move' ? moveTo : null,
      month,
    })
    onDeleted(result.change_id)
    onClose()
  }

  return (
    <Modal onClose={onClose} className="delete-category-modal__overlay" dismissOnBackdrop={false}>
      <div
        className="delete-category-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Delete ${target.name}`}
      >
        <h2 className="delete-category-modal__title">Delete {target.name}?</h2>

        {isLoading && <p className="delete-category-modal__loading">Checking what this affects…</p>}

        {isError && (
          <div className="delete-category-modal__error" role="alert">
            <p>Couldn&rsquo;t check what this delete affects — nothing was deleted.</p>
            <button type="button" onClick={() => refetch()}>
              Try again
            </button>
          </div>
        )}

        {blocked && (
          <div className="delete-category-modal__blocked" role="alert">
            <AlertTriangle size={15} />
            <div>
              {preview!.blocked_by.map((reason) => (
                <p key={reason}>{reason}</p>
              ))}
            </div>
          </div>
        )}

        {preview && !blocked && (
          <>
            <dl className="delete-category-modal__facts">
              {target.kind === 'group' && (
                <div>
                  <dt>Categories</dt>
                  <dd>{preview.category_names.join(', ') || 'None'}</dd>
                </div>
              )}
              <div>
                <dt>Transactions</dt>
                <dd>
                  {txnCount}
                  {preview.reconciled_count > 0 && (
                    <span className="delete-category-modal__note">
                      <Lock size={11} /> {preview.reconciled_count} reconciled
                    </span>
                  )}
                </dd>
              </div>
              {movingActivity !== 0 && (
                <div>
                  <dt>Spending recorded in it</dt>
                  <dd>{formatMoney(movingActivity)}</dd>
                </div>
              )}
              <div>
                <dt>Returns to Ready to Assign</dt>
                <dd className="delete-category-modal__money">{formatMoney(returning)}</dd>
              </div>
              {preview.payee_count > 0 && (
                <div>
                  <dt>Payee defaults cleared</dt>
                  <dd>{preview.payee_count}</dd>
                </div>
              )}
              {preview.scheduled_count > 0 && (
                <div>
                  <dt>Scheduled transactions cleared</dt>
                  <dd>{preview.scheduled_count}</dd>
                </div>
              )}
            </dl>

            {txnCount > 0 && (
              <fieldset className="delete-category-modal__choice">
                <legend>What happens to the transactions?</legend>

                <label className="delete-category-modal__option">
                  <input
                    type="radio"
                    name="disposition"
                    checked={mode === 'move'}
                    onChange={() => setMode('move')}
                  />
                  <span>
                    <strong>Move them to another category</strong>
                    <em>
                      Keeps this spending in reports, under the category you pick — and the
                      money that covered it moves too, so that category&rsquo;s balance is not
                      affected.
                    </em>
                  </span>
                </label>
                {mode === 'move' && (
                  <div className="delete-category-modal__picker">
                    <CategoryCombobox
                      value={moveTo}
                      onChange={setMoveTo}
                      groups={destinations}
                      placeholder="Choose a category…"
                      sheetTitle="Move transactions to"
                      aria-label="Move transactions to"
                    />
                  </div>
                )}

                <label className="delete-category-modal__option">
                  <input
                    type="radio"
                    name="disposition"
                    checked={mode === 'uncategorize'}
                    onChange={() => setMode('uncategorize')}
                  />
                  <span>
                    <strong>Leave them uncategorized</strong>
                    <em>
                      They&rsquo;ll show &ldquo;Needs Category&rdquo; with a note saying what they
                      used to be, and drop out of reports that group by category until you file
                      them.
                    </em>
                  </span>
                </label>
              </fieldset>
            )}

            {preview.references.length > 0 && (
              // What else points at this category. Named rather than severed
              // silently: a saved view losing its layout is the user's to know
              // about, and a recorded money move is why the row is kept at all.
              <div className="delete-category-modal__refs">
                <p className="delete-category-modal__refs-title">Also pointing at it:</p>
                <ul>
                  {preview.references.map((r) => (
                    <li key={r.kind}>
                      {r.label}
                      {r.clearable ? '' : ' — kept, so this stays in the budget’s history'}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <p className="delete-category-modal__undo">
              This can be undone from Activity.{' '}
              {preview.may_hard_delete
                ? 'Nothing else refers to it, so the category itself is removed.'
                : 'The category is kept as deleted history, so the records that mention it can still name it.'}
            </p>
          </>
        )}

        <div className="delete-category-modal__actions">
          <button type="button" className="delete-category-modal__cancel" onClick={onClose}>
            Cancel
          </button>
          {/* The third choice, and the one that loses nothing. Gated on the
              archive endpoint's own `may_archive` rather than the delete
              preview's `blocked_by`: the two refuse on different grounds, and
              reading the delete's answer here offered the button on an
              envelope the archive would then refuse over its balance. */}
          <button
            type="button"
            className="delete-category-modal__archive"
            onClick={handleArchive}
            disabled={!preview || !mayArchive || archiveCategories.isPending}
            title={
              archiveBlockedBy
                ? `Cannot archive: ${archiveBlockedBy}`
                : 'Keep its history and stop new use, instead of deleting'
            }
          >
            {archiveCategories.isPending ? 'Archiving…' : 'Archive instead'}
          </button>
          <button
            type="button"
            className="delete-category-modal__confirm"
            onClick={handleDelete}
            disabled={!preview || blocked || deleteCategories.isPending || needsDestination}
          >
            {deleteCategories.isPending ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
