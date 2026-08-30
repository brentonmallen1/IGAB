import { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { Surface } from '../../common/Surface'
import { Dialog } from '../../common/Dialog/Dialog'
import { TagChip, type TagColorSlot } from '../../common/TagChip'
import { TagPicker, type TagOption } from '../../common/TagPicker'
import { HygieneFindings } from '../../accounts/HygieneFindings'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import {
  useAccountHygiene,
  useAccounts,
  useUpdateAccount,
  type HygieneFinding,
} from '../../../api/accounts'
import {
  useBulkSetCategoryTags,
  useCreateTag,
  useTagSuggestions,
  useTags,
} from '../../../api/tags'
import { useMarkImportReviewed, type YnabImportResult } from '../../../api/imports'
import { apiErrorMessage } from '../../../api/client'
import { renderableCategories, renderableGroups } from '../../budget/budgetGroups'
import { useFormatters } from '../../../hooks/useFormatters'
import { parseApiDecimal } from '../../../utils/money'
import {
  buildRows,
  filterRows,
  initialFilter,
  pendingUpdates,
  repairableTransferLegs,
  setTags,
  stepsFor,
  toggleTag,
  type Draft,
  type ReviewCategory,
  type ReviewRow,
  type RowFilter,
  type StepId,
} from './importReview'
import './ImportReviewDialog.css'

/**
 * What the import decided, and a chance to change it.
 *
 * The report half used to be a stack of up to six toasts fired while the app
 * was changing route; the adjustable half — which categories were given a
 * classification-overriding tag — could only be reached through a panel of the
 * category inspector nobody had a reason to open. Both are here, once.
 *
 * The two halves are sourced differently on purpose. The report is read from
 * the stored summary, because it records an event that cannot be re-derived.
 * The tags and accounts are read live, so a review reopened months later is
 * about the budget as it is rather than as it arrived.
 *
 * Nothing is written until Done. A suggestion is a proposal, and a proposal
 * that applied itself would be the silent tagging this exists to replace.
 */
export function ImportReviewDialog({
  budgetId,
  summary,
  onClose,
}: {
  budgetId: string
  summary: YnabImportResult | null
  onClose: () => void
}) {
  const steps = stepsFor(summary)
  const [stepIndex, setStepIndex] = useState(0)
  const [draft, setDraft] = useState<Draft>({})
  const [filter, setFilter] = useState<RowFilter>(() => initialFilter(summary))

  const { data: categories } = useCategories(budgetId, true)
  const { data: groups } = useCategoryGroups(budgetId, true)
  const { data: tags } = useTags(budgetId)
  const { data: suggestions } = useTagSuggestions(budgetId)
  const { data: hygiene } = useAccountHygiene(budgetId)
  const bulkSetTags = useBulkSetCategoryTags(budgetId)
  const createTag = useCreateTag(budgetId)
  const markReviewed = useMarkImportReviewed(budgetId)

  const systemTags = useMemo(() => (tags ?? []).filter((t) => t.system_key), [tags])
  const keyById = useMemo(
    () => Object.fromEntries(systemTags.map((t) => [t.id, t.system_key as string])),
    [systemTags]
  )
  const tagByKey = useMemo(
    () => Object.fromEntries(systemTags.map((t) => [t.system_key as string, t])),
    [systemTags]
  )
  const tagById = useMemo(() => Object.fromEntries((tags ?? []).map((t) => [t.id, t])), [tags])
  // Every tag in the budget, system and the user's own alike. The review can
  // replace a category's whole set, so it has to be able to offer the whole
  // set — the suggestions are a shortcut, not the only way in.
  const tagOptions: TagOption[] = useMemo(
    () => (tags ?? []).map((t) => ({ id: t.id, name: t.name, color_slot: t.color_slot })),
    [tags]
  )

  const reviewable: ReviewCategory[] = useMemo(() => {
    if (!categories || !groups) return []
    // The same rule the grid uses for which groups exist, and the same one the
    // server scopes suggestions by: income holds no envelope money, so
    // classifying its spending is meaningless.
    const names = new Map(renderableGroups(groups).map((g) => [g.id, g.name]))
    // `renderableGroups` drops system groups, not hidden ones, so the card
    // envelopes' group survives it — and a set-aside envelope cannot carry a
    // classification tag, since nothing is ever filed to it.
    return renderableCategories(categories)
      .filter((c) => names.has(c.category_group_id))
      .map((c) => ({
        id: c.id,
        name: c.name,
        groupName: names.get(c.category_group_id) as string,
        hidden: c.is_archived,
        tagIds: (c.tags ?? []).map((t) => t.id),
      }))
  }, [categories, groups])

  const rows = useMemo(
    () =>
      buildRows(reviewable, suggestions ?? [], summary?.tagged_categories ?? [], keyById, draft),
    [reviewable, suggestions, summary, keyById, draft]
  )
  const shown = filterRows(rows, filter, draft)
  const updates = pendingUpdates(draft, reviewable)

  async function finish() {
    try {
      if (updates.length > 0) await bulkSetTags.mutateAsync(updates)
      await markReviewed.mutateAsync()
      if (updates.length > 0) {
        toast.success(
          `Updated tags on ${updates.length} categor${updates.length === 1 ? 'y' : 'ies'}.`
        )
      }
      onClose()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not save those tag changes'))
    }
  }

  const step = steps[stepIndex]
  const saving = bulkSetTags.isPending || markReviewed.isPending
  const last = stepIndex === steps.length - 1

  return (
    <Dialog
      title="Import review"
      onClose={onClose}
      historyKey="import-review"
      width="lg"
      footer={
        <>
          <button
            type="button"
            className="import-review__btn"
            onClick={() => setStepIndex((i) => i - 1)}
            disabled={stepIndex === 0 || saving}
          >
            Back
          </button>
          <span className="import-review__pending">
            {updates.length > 0 &&
              `${updates.length} categor${updates.length === 1 ? 'y' : 'ies'} to update`}
          </span>
          {last ? (
            <button type="button" className="import-review__btn import-review__btn--primary" onClick={finish} disabled={saving}>
              {saving ? 'Saving…' : updates.length > 0 ? 'Save and close' : 'Done'}
            </button>
          ) : (
            <button
              type="button"
              className="import-review__btn import-review__btn--primary"
              onClick={() => setStepIndex((i) => i + 1)}
              disabled={saving}
            >
              Next
            </button>
          )}
        </>
      }
    >
      <StepRail steps={steps} current={stepIndex} onPick={setStepIndex} />

      {step === 'summary' && summary && <SummaryStep summary={summary} />}
      {step === 'tags' && (
        <TagsStep
          rows={rows}
          shown={shown}
          filter={filter}
          onFilter={setFilter}
          tagByKey={tagByKey}
          tagById={tagById}
          tagOptions={tagOptions}
          onToggle={(category, tagId) => setDraft((d) => toggleTag(d, category, tagId))}
          onSetTags={(category, tagIds) => setDraft((d) => setTags(d, category, tagIds))}
          onCreateTag={async (name) => {
            // The tag itself has to exist before it can be assigned, so this
            // one call writes immediately. It lands on no category until Done.
            const tag = await createTag.mutateAsync({ name })
            return { id: tag.id, name: tag.name, color_slot: tag.color_slot }
          }}
          onAcceptAll={() =>
            setDraft((d) =>
              shown.reduce(
                (acc, row) =>
                  row.suggestions.reduce(
                    (inner, s) =>
                      tagByKey[s.systemKey]
                        ? toggleTag(inner, row.category, tagByKey[s.systemKey].id)
                        : inner,
                    acc
                  ),
                d
              )
            )
          }
        />
      )}
      {step === 'accounts' && (
        <AccountsStep
          summary={summary}
          findings={hygiene?.findings ?? []}
          budgetId={budgetId}
          onNavigate={onClose}
        />
      )}
    </Dialog>
  )
}

const STEP_LABELS: Record<StepId, string> = {
  summary: 'What arrived',
  tags: 'Categories & tags',
  accounts: 'Accounts',
}

function StepRail({
  steps,
  current,
  onPick,
}: {
  steps: StepId[]
  current: number
  onPick: (i: number) => void
}) {
  return (
    <nav className="import-review__rail" aria-label="Review steps">
      {steps.map((id, i) => (
        <button
          key={id}
          type="button"
          className={`import-review__step ${i === current ? 'import-review__step--on' : ''}`}
          aria-current={i === current ? 'step' : undefined}
          onClick={() => onPick(i)}
        >
          <span className="import-review__step-n">{i + 1}</span>
          {STEP_LABELS[id]}
        </button>
      ))}
    </nav>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="import-review__stat">
      <span className="import-review__stat-v tabular">{value}</span>
      <span className="import-review__stat-l">{label}</span>
    </div>
  )
}

function SummaryStep({ summary }: { summary: YnabImportResult }) {
  const { formatMoney } = useFormatters()
  const reserves = parseApiDecimal(summary.credit_card_payment_reserves_skipped)
  const repairable = repairableTransferLegs(summary)

  const leftOut = [
    summary.accounts_skipped > 0 &&
      `${n(summary.accounts_skipped)} account${summary.accounts_skipped === 1 ? '' : 's'} left out at your request, and ${n(summary.transactions_excluded)} of their transactions with them.`,
    summary.accounts_closed > 0 &&
      `${n(summary.accounts_closed)} account${summary.accounts_closed === 1 ? '' : 's'} imported in full and then closed — every transaction arrived, only the account is hidden from pickers.`,
    summary.credit_card_payment_assignments_skipped > 0 &&
      `${n(summary.credit_card_payment_assignments_skipped)} credit-card payment assignment${summary.credit_card_payment_assignments_skipped === 1 ? '' : 's'} (${formatMoney(reserves)}) had no matching card here — the card was left out of the import or is not on budget — so those reserves were not carried over.`,
    summary.tracking_account_categories_stripped > 0 &&
      `${n(summary.tracking_account_categories_stripped)} row${summary.tracking_account_categories_stripped === 1 ? '' : 's'} on tracking accounts arrived with a category and imported without one — off-budget activity is net-worth movement, not budget spending.`,
    summary.skipped > 0 &&
      `${n(summary.skipped)} rows skipped as duplicates of something already here.`,
    repairable > 0 &&
      `${n(repairable)} transfer legs arrived without their other side${summary.transfer_legs_in_splits > 0 ? `, plus ${n(summary.transfer_legs_in_splits)} inside splits that can never be paired` : ''}. The Accounts step can match them up.`,
  ].filter(Boolean) as string[]

  return (
    <>
      <Surface variant="sunken" title="What arrived" className="import-review__block">
        <div className="import-review__stats">
          <Stat label="transactions" value={n(summary.transactions)} />
          <Stat label="accounts" value={n(summary.accounts)} />
          <Stat label="categories" value={n(summary.categories)} />
          <Stat label="groups" value={n(summary.category_groups)} />
          <Stat label="budget assignments" value={n(summary.assignments)} />
        </div>
      </Surface>

      {summary.parity && <ParityBlock parity={summary.parity} />}

      {leftOut.length > 0 && (
        <Surface variant="sunken" title="What was left out" className="import-review__block">
          <ul className="import-review__notes">
            {leftOut.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Surface>
      )}

      {summary.errors.length > 0 && (
        <Surface
          variant="sunken"
          title={`${n(summary.errors.length)} rows had problems`}
          className="import-review__block"
        >
          {/* Every one of them. The toast showed the first and discarded up to
              forty-nine more. */}
          <ul className="import-review__errors scroll-list">
            {summary.errors.map((e, i) => (
              <li key={`${i}-${e}`}>{e}</li>
            ))}
          </ul>
        </Surface>
      )}
    </>
  )
}

/** A grouped count, so five figures read as counts and not as amounts. */
const n = (v: number) => v.toLocaleString()

/** A whole-number share, for counts the reader is meant to weigh rather
 *  than audit. Zero out of zero is 0%, never NaN%. */
function percent(part: number, whole: number): string {
  return whole === 0 ? '0%' : `${Math.round((part / whole) * 100)}%`
}

function verdictModifier(matches: boolean, incoherent: boolean): string {
  if (incoherent) return 'import-review__verdict--warn'
  return matches ? 'import-review__verdict--ok' : ''
}

function ParityBlock({ parity }: { parity: NonNullable<YnabImportResult['parity']> }) {
  const { formatMoney, formatDate } = useFormatters()
  const igab = parseApiDecimal(parity.igab_ready_to_assign)
  const ynab = parseApiDecimal(parity.ynab_ready_to_assign)
  const expected = parseApiDecimal(parity.expected_ready_to_assign)
  const debt = parseApiDecimal(parity.uncovered_card_debt)
  const unfiled = parseApiDecimal(parity.uncategorized_net)

  // An export whose own numbers contradict each other cannot be compared
  // against: IGAB rebuilds every balance from the transactions in the file,
  // while the figure it is held to is the Available column shipped beside
  // them. Where those two disagree, the difference measures the file.
  const { consistency } = parity
  const incoherent = !consistency.self_consistent

  const notes = [
    incoherent &&
      consistency.carryover_rows_violating > 0 &&
      `${percent(consistency.carryover_rows_violating, consistency.carryover_rows_checked)} of its plan rows (${n(consistency.carryover_rows_violating)} of ${n(consistency.carryover_rows_checked)}) do not match YNAB's own running balance.`,
    incoherent &&
      consistency.activity_cells_disagreeing > 0 &&
      `${percent(consistency.activity_cells_disagreeing, consistency.activity_cells_checked)} of its activity figures (${n(consistency.activity_cells_disagreeing)} of ${n(consistency.activity_cells_checked)}) do not match the transactions shipped in the same file.`,
    debt !== 0 &&
      `${formatMoney(Math.abs(debt))} is card debt with nothing set aside behind it — both apps leave it out of Ready to Assign; here it shows as Uncovered in the cards section.`,
    unfiled !== 0 &&
      `${formatMoney(Math.abs(unfiled))} of uncategorized transactions stays out of Ready to Assign until you file it; YNAB leaves it out of its plan entirely.`,
    parity.categories_pending > 0 &&
      `${parity.categories_pending} categor${parity.categories_pending === 1 ? 'y differs' : 'ies differ'} only by uncleared rows YNAB has not approved yet.`,
    parity.categories_unmatched > 0 &&
      `${parity.categories_unmatched} categor${parity.categories_unmatched === 1 ? 'y YNAB priced was' : 'ies YNAB priced were'} not compared — no category here answers to that name.`,
  ].filter(Boolean) as string[]

  return (
    <Surface
      variant="sunken"
      title="Checked against the export"
      className="import-review__block"
      actions={<span className="import-review__asof">as of {formatDate(parity.month)}</span>}
    >
      <div className="import-review__parity">
        <Stat label="Ready to Assign here" value={formatMoney(igab)} />
        <Stat label="YNAB's own figures" value={formatMoney(ynab)} />
        {expected !== ynab && <Stat label="expected here" value={formatMoney(expected)} />}
      </div>
      <p
        className={`import-review__verdict ${verdictModifier(parity.matches, incoherent)}`}
      >
        {incoherent
          ? `This export does not agree with itself, so it cannot say whether the import was faithful. ${parity.categories_differing} of ${parity.categories_compared} categories differ from the figures it shipped.`
          : parity.matches
            ? `Ready to Assign matches YNAB, and every envelope agrees across ${parity.categories_compared} categories.`
            : `${parity.categories_differing} of ${parity.categories_compared} categories differ.`}
      </p>
      {!parity.matches && parity.top_differences.length > 0 && (
        <ul className="import-review__diffs">
          {parity.top_differences.map((d) => (
            <li key={d.name}>
              <span className="import-review__diff-n">{d.name}</span>
              <span className="tabular">
                {formatMoney(parseApiDecimal(d.igab))} here vs{' '}
                {formatMoney(parseApiDecimal(d.ynab))} in YNAB
              </span>
            </li>
          ))}
        </ul>
      )}
      {parity.cards_differing > 0 && (
        <>
          <p className="import-review__verdict import-review__verdict--warn">
            {parity.cards_differing} of {parity.cards_compared} card reserve
            {parity.cards_differing === 1 ? ' differs' : 's differ'} from the amount YNAB had set
            aside — the card's Ready to pay may not match what it owes.
          </p>
          <ul className="import-review__diffs">
            {parity.card_differences.map((d) => (
              <li key={d.name}>
                <span className="import-review__diff-n">{d.name}</span>
                <span className="tabular">
                  {formatMoney(parseApiDecimal(d.igab))} here vs{' '}
                  {formatMoney(parseApiDecimal(d.ynab))} in YNAB
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {notes.length > 0 && (
        <ul className="import-review__notes">
          {notes.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </Surface>
  )
}

function TagsStep({
  rows,
  shown,
  filter,
  onFilter,
  tagByKey,
  tagById,
  tagOptions,
  onToggle,
  onSetTags,
  onCreateTag,
  onAcceptAll,
}: {
  rows: ReviewRow[]
  shown: ReviewRow[]
  filter: RowFilter
  onFilter: (f: RowFilter) => void
  tagByKey: Record<string, { id: string; name: string; color_slot: string | null }>
  tagById: Record<string, { id: string; name: string; color_slot: string | null }>
  tagOptions: TagOption[]
  onToggle: (category: ReviewCategory, tagId: string) => void
  onSetTags: (category: ReviewCategory, tagIds: string[]) => void
  onCreateTag: (name: string) => Promise<TagOption>
  onAcceptAll: () => void
}) {
  const decidedCount = rows.filter((r) => r.importTagged).length
  const suggestedCount = rows.filter((r) => r.suggestions.length > 0).length
  const openSuggestions = shown.reduce((n, r) => n + r.suggestions.length, 0)

  return (
    <>
      <p className="dialog__body">
        A tag decides how a category's spending is counted — money leaving one
        tagged Savings is saving, not spending, and what you mark Essential is
        what an emergency fund is measured against. These are the ones the
        import guessed, plus what the names suggest.
      </p>

      <div className="import-review__filters" role="group" aria-label="Which categories to show">
        {(
          [
            ['decided', `Tagged by the import (${decidedCount})`],
            ['suggested', `Suggested (${suggestedCount})`],
            ['all', `All (${rows.length})`],
          ] as [RowFilter, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`import-review__chip ${filter === id ? 'import-review__chip--on' : ''}`}
            aria-pressed={filter === id}
            onClick={() => onFilter(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Offered once above the list, not on every row — twenty identical
          per-row notes is a wall to scroll past. */}
      {openSuggestions > 0 && (
        <p className="import-review__bulk">
          {openSuggestions} suggestion{openSuggestions === 1 ? '' : 's'} in this list.
          <button type="button" className="dialog__link" onClick={onAcceptAll}>
            Accept them all
          </button>
        </p>
      )}

      <Surface variant="sunken" className="import-review__rows">
        {shown.length === 0 && (
          <p className="import-review__empty">
            Nothing here. Try <strong>All</strong> to tag a category by hand.
          </p>
        )}
        {shown.map((row) => (
          <div key={row.category.id} className="import-review__row">
            <div className="import-review__cat">
              <span className="import-review__cat-n">
                {row.category.name}
                {row.category.hidden && (
                  <span className="import-review__hidden" title="Hidden on the budget page">
                    hidden
                  </span>
                )}
              </span>
              <span className="import-review__cat-g">{row.category.groupName}</span>
              {row.importTagged && row.importMatchedOn && (
                <span className="import-review__why">
                  tagged from “{row.importMatchedOn}”
                </span>
              )}
            </div>
            <div className="import-review__tags">
              {/* Every tag it carries, not only the system ones — this row can
                  replace the whole set, so it has to show the whole set. */}
              {row.tagIds.map((id) =>
                tagById[id] ? (
                  <TagChip
                    key={id}
                    name={tagById[id].name}
                    colorSlot={tagById[id].color_slot as TagColorSlot | null}
                    size="sm"
                    onRemove={() => onToggle(row.category, id)}
                  />
                ) : null
              )}
              {row.suggestions.map((s) =>
                tagByKey[s.systemKey] ? (
                  <label key={s.systemKey} className="import-review__offer">
                    <input
                      type="checkbox"
                      checked={false}
                      onChange={() => onToggle(row.category, tagByKey[s.systemKey].id)}
                    />
                    <span>{tagByKey[s.systemKey].name}?</span>
                    <span className="import-review__why">from “{s.matchedOn}”</span>
                  </label>
                ) : null
              )}
              {/* The way in for everything the hints never thought of: any tag
                  in the budget, on any category, however many. Without it a
                  row with no tags and no suggestion had nothing to offer. */}
              <TagPicker
                selectedTagIds={row.tagIds}
                tags={tagOptions}
                onChange={(tagIds) => onSetTags(row.category, tagIds)}
                onCreateTag={onCreateTag}
                allowCreate
                triggerLabel="+ Tag"
                ghost
              />
            </div>
          </div>
        ))}
      </Surface>
    </>
  )
}

function AccountsStep({
  summary,
  findings,
  budgetId,
  onNavigate,
}: {
  summary: YnabImportResult | null
  findings: HygieneFinding[]
  budgetId: string
  onNavigate: () => void
}) {
  const { data: accounts } = useAccounts(budgetId, { includeClosed: true })
  const update = useUpdateAccount(budgetId)
  const closed = (accounts ?? []).filter((a) => a.is_closed)

  return (
    <>
      {findings.length > 0 ? (
        <Surface
          variant="sunken"
          title="Worth a look"
          className="import-review__block"
        >
          <HygieneFindings findings={findings} budgetId={budgetId} onNavigate={onNavigate} />
        </Surface>
      ) : (
        <p className="dialog__body">
          Nothing about these accounts looks wrong. Types, budget membership and
          transfers all check out.
        </p>
      )}

      {closed.length > 0 && (
        <Surface
          variant="sunken"
          title={`${closed.length} account${closed.length === 1 ? '' : 's'} imported and closed`}
          className="import-review__block"
        >
          <p className="dialog__body dialog__body--muted">
            Every transaction arrived — reports and net worth are untouched. Closing only takes
            an account out of the pickers and report filters. This is the one thing the import
            did that nothing else offers to undo.
          </p>
          <div className="import-review__reopen">
            {closed.map((a) => (
              <button
                key={a.id}
                type="button"
                className="import-review__btn"
                disabled={update.isPending}
                onClick={() => update.mutate({ id: a.id, is_closed: false })}
              >
                Reopen {a.name}
              </button>
            ))}
          </div>
        </Surface>
      )}

      {summary && summary.accounts_skipped > 0 && (
        <Surface variant="sunken" title="What was left out" className="import-review__block">
          <p className="dialog__body">
            {summary.accounts_skipped} account
            {summary.accounts_skipped === 1 ? ' was' : 's were'} left out entirely, along with{' '}
            {summary.transactions_excluded.toLocaleString()} of their transactions. That is
            usually what leaves transfers without their other side. Re-import the export to
            bring one in.
          </p>
        </Surface>
      )}
    </>
  )
}
