import { useRef, useState, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronUp, GitMerge, Regex, Sparkles, Tag } from 'lucide-react'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import {
  usePayees,
  useUpdatePayee,
  useDeletePayee,
  useMergePayee,
  useFetchPayeeDuplicates,
  type PayeeWithCount,
} from '../../api/payees'
import { usePayeeTransactions } from '../../api/transactions'
import { useFormatters } from '../../hooks/useFormatters'
import { useTags, useBulkAddPayeeTags, useCreateTag, useSetPayeeTags } from '../../api/tags'
import { useAIStatus, useSuggestRegex } from '../../api/ai'
import { PayeeMergeModal } from '../../components/payees/PayeeMergeModal/PayeeMergeModal'
import type { MergeConfig } from '../../components/payees/PayeeMergeModal/PayeeMergeModal'
import { FloatingSelectionBar } from '../../components/common/FloatingSelectionBar/FloatingSelectionBar'
import { Dialog } from '../../components/common/Dialog/Dialog'
import { suggestPayeeRegex, testPattern } from '../../utils/payeeRegex'
import { dedupeSamples, samplesFromLines } from '../../utils/payeeSamples'
import {
  PatternCandidates,
  PatternMatchPreview,
} from '../../components/payees/PatternSuggest/PatternSuggest'
import {
  NO_PATTERN_MESSAGE,
  patternCandidates,
} from '../../components/payees/PatternSuggest/patternCandidates'
import { TagChip } from '../../components/common/TagChip'
import { TagPicker, type TagOption } from '../../components/common/TagPicker'
import './PayeesPage.css'
import { confirmAsync } from '../../stores/confirmStore'
import toast from 'react-hot-toast'

type WizardGroup = {
  label: string
  payees: Array<{ id: string; name: string; transaction_count?: number }>
}

const PEEK_LIMIT = 5

/** A few recent transactions for one merge candidate, so the user can tell
 * Lowes from Lowes Food before deciding what belongs in the merge. */
function PayeeTransactionPeek({ budgetId, payeeId }: { budgetId: string; payeeId: string }) {
  const { data, isLoading } = usePayeeTransactions(budgetId, payeeId, PEEK_LIMIT)
  const { formatMoney, formatDate } = useFormatters()

  if (isLoading) return <div className="payees-peek payees-peek--muted">Loading…</div>
  const txns = data?.transactions ?? []
  if (txns.length === 0)
    return <div className="payees-peek payees-peek--muted">No transactions.</div>
  return (
    <div className="payees-peek">
      {txns.map((t) => (
        <div key={t.id} className="payees-peek__row">
          <span className="payees-peek__date">{formatDate(t.date)}</span>
          <span className="payees-peek__memo">{t.memo || t.import_description || '—'}</span>
          <span className="payees-peek__amount">{formatMoney(t.amount)}</span>
        </div>
      ))}
      {data && data.total_count > txns.length && (
        <div className="payees-peek__more">
          {txns.length} most recent of {data.total_count}
        </div>
      )}
    </div>
  )
}

export function PayeesPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: payees = [], isLoading } = usePayees(budgetId)
  const updatePayee = useUpdatePayee(budgetId)
  const deletePayee = useDeletePayee(budgetId)
  const mergePayee = useMergePayee(budgetId)
  const fetchDuplicates = useFetchPayeeDuplicates(budgetId)
  const aiStatus = useAIStatus()
  const suggestRegex = useSuggestRegex(budgetId ?? '')
  const { data: allTags = [] } = useTags(budgetId)
  const bulkAddTags = useBulkAddPayeeTags(budgetId)
  const setPayeeTags = useSetPayeeTags(budgetId)
  const createTag = useCreateTag(budgetId)

  const { selectedPayeeIds, togglePayeeSelection, selectAllPayees, clearPayeeSelection } =
    useUIStore()

  const [searchParams] = useSearchParams()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editMappings, setEditMappings] = useState('')
  const [editPattern, setEditPattern] = useState('')
  const [editAiCandidates, setEditAiCandidates] = useState<string[]>([])
  const [search, setSearch] = useState(searchParams.get('q') ?? '')
  const [showMergeModal, setShowMergeModal] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [wizardGroups, setWizardGroups] = useState<WizardGroup[]>([])
  const [wizardIdx, setWizardIdx] = useState(0)
  const [wizardChecked, setWizardChecked] = useState<Set<string>>(new Set())
  const [wizardPeekId, setWizardPeekId] = useState<string | null>(null)
  const [wizardMergePayees, setWizardMergePayees] = useState<PayeeWithCount[] | null>(null)
  const [showCleanupModal, setShowCleanupModal] = useState(false)
  const [sensitivity, setSensitivity] = useState<'strict' | 'balanced' | 'loose'>('balanced')
  const [showBulkTagPicker, setShowBulkTagPicker] = useState(false)
  const [sortColumn, setSortColumn] = useState<'name' | 'transactions'>('name')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')

  const headerCheckboxRef = useRef<HTMLInputElement>(null)

  const filtered = useMemo(() => {
    const term = search.toLowerCase()
    return payees
      .filter((p) => {
        if (p.transfer_account_id) return false
        const searchTarget =
          `${p.name} ${p.mapping_samples.join(' ')} ${p.match_pattern || ''}`.toLowerCase()
        return searchTarget.includes(term)
      })
      .sort((a, b) => {
        let cmp: number
        if (sortColumn === 'name') {
          cmp = a.name.localeCompare(b.name)
        } else {
          cmp = a.transaction_count - b.transaction_count
        }
        return sortDirection === 'asc' ? cmp : -cmp
      })
  }, [payees, search, sortColumn, sortDirection])

  // Below the hooks, not above them. This guard used to sit before the useMemo
  // above, so the number of hooks this component called changed with
  // budgetId — React's rules-of-hooks violation, and the kind that only shows
  // up when a budget is selected after the page has already rendered without
  // one. Every hook above already handles a null budgetId.
  if (!budgetId) {
    return (
      <div className="payees-page">
        <div className="payees-empty">Select a budget to manage payees.</div>
      </div>
    )
  }

  const totalPayees = payees.filter((p) => !p.transfer_account_id).length
  const filteredIds = filtered.map((p) => p.id)
  const allOrderedIds = filtered.map((p) => p.id)
  const selectedInFiltered = filteredIds.filter((id) => selectedPayeeIds.has(id))
  const allFilteredSelected = filtered.length > 0 && selectedInFiltered.length === filtered.length
  const someFilteredSelected = selectedInFiltered.length > 0

  if (headerCheckboxRef.current) {
    headerCheckboxRef.current.indeterminate = someFilteredSelected && !allFilteredSelected
  }

  function handleSelectAllFiltered() {
    if (allFilteredSelected) {
      const keep = [...selectedPayeeIds].filter((id) => !filteredIds.includes(id))
      selectAllPayees(keep)
    } else {
      const union = new Set([...selectedPayeeIds, ...filteredIds])
      selectAllPayees([...union])
    }
  }

  function handleSort(column: 'name' | 'transactions') {
    if (sortColumn === column) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortColumn(column)
      setSortDirection('asc')
    }
  }

  const SortIcon = sortDirection === 'asc' ? ChevronUp : ChevronDown

  function startEdit(id: string, name: string, samples: string[], pattern: string | null) {
    setEditingId(id)
    setEditName(name)
    setEditMappings(samples.join('\n'))
    setEditPattern(pattern ?? '')
    setEditAiCandidates([])
  }

  async function saveEdit(id: string) {
    const pattern = editPattern.trim()
    if (pattern && testPattern(pattern, '') === null) {
      toast.error('That match pattern is not a valid regular expression.')
      return
    }
    if (editName.trim()) {
      await updatePayee.mutateAsync({
        id,
        name: editName.trim(),
        mapping_samples: samplesFromLines(editMappings),
        match_pattern: pattern || null,
      })
    }
    setEditingId(null)
  }

  async function handleDelete(id: string, name: string) {
    const ok = await confirmAsync({
      title: `Delete payee "${name}"?`,
      message: 'Transactions will have no payee.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    await deletePayee.mutateAsync(id)
    clearPayeeSelection()
  }

  async function executeMergeWith(mergeList: PayeeWithCount[], config: MergeConfig) {
    const { targetId, addToMappingSamples, customName, matchPattern } = config
    const target = payees.find((p) => p.id === targetId)
    const sources = mergeList.filter((p) => p.id !== targetId)
    if (!target) return

    const absorbedPayees = customName ? mergeList : sources

    const update: { name?: string; mapping_samples?: string[]; match_pattern?: string } = {}
    if (customName) update.name = customName
    if (matchPattern) update.match_pattern = matchPattern

    if (addToMappingSamples && absorbedPayees.length > 0) {
      // The same list the modal previewed: the survivor's samples (unless it
      // is being renamed), then the absorbed names and their samples.
      update.mapping_samples = dedupeSamples([
        ...(customName ? [] : target.mapping_samples),
        ...absorbedPayees.map((p) => p.name),
        ...absorbedPayees.flatMap((p) => p.mapping_samples),
      ])
    }

    if (Object.keys(update).length > 0) {
      await updatePayee.mutateAsync({ id: targetId, ...update })
    }

    for (const source of sources) {
      await mergePayee.mutateAsync({ sourceId: source.id, targetId })
    }
  }

  async function executeMerge(config: MergeConfig) {
    await executeMergeWith(selectedPayees, config)
    setShowMergeModal(false)
    clearPayeeSelection()
  }

  const sensitivityThresholds = { loose: 70, balanced: 75, strict: 80 }

  async function runCleanup() {
    setShowCleanupModal(false)
    const threshold = sensitivityThresholds[sensitivity]
    const result = await fetchDuplicates.mutateAsync(threshold)
    if (result && result.length > 0) {
      openWizard(
        result.map((g) => ({
          label: `${g.similarity}% similar`,
          payees: g.payees,
        }))
      )
    } else {
      toast.success('No duplicate payees found.')
    }
  }

  function openWizard(groups: WizardGroup[]) {
    setWizardGroups(groups)
    goToWizardGroup(groups, 0)
    setShowWizard(true)
  }

  // Every checkbox starts checked when a group comes into view.
  function goToWizardGroup(groups: WizardGroup[], idx: number) {
    setWizardIdx(idx)
    setWizardChecked(new Set(groups[idx]?.payees.map((p) => p.id)))
    setWizardPeekId(null)
  }

  function startWizardMerge() {
    if (checkedPayees.length < 2) return
    setWizardMergePayees(checkedPayees)
  }

  async function executeWizardMerge(config: MergeConfig) {
    if (!wizardMergePayees || !currentGroup) return
    await executeMergeWith(wizardMergePayees, config)
    setWizardMergePayees(null)
    // The unchecked leftovers may still be duplicates of each other
    // (Lowes Food vs Lowes Foods) — keep them as a group if a merge is
    // still possible, otherwise the group is done.
    const leftover = currentGroup.payees.filter((p) => !wizardChecked.has(p.id))
    const remaining = wizardGroups
      .map((g, i) =>
        i !== wizardIdx ? g : leftover.length >= 2 ? { ...g, payees: leftover } : null
      )
      .filter((g): g is WizardGroup => g !== null)
    setWizardGroups(remaining)
    if (remaining.length === 0) {
      setShowWizard(false)
    } else {
      goToWizardGroup(remaining, Math.min(wizardIdx, remaining.length - 1))
    }
  }

  function nextWizard() {
    if (wizardIdx + 1 >= wizardGroups.length) {
      setShowWizard(false)
    } else {
      goToWizardGroup(wizardGroups, wizardIdx + 1)
    }
  }

  function prevWizard() {
    goToWizardGroup(wizardGroups, Math.max(0, wizardIdx - 1))
  }

  const currentGroup = wizardGroups[wizardIdx]
  // Full payee records for the checked wizard rows — the merge modal needs
  // mapping samples and patterns, which the suggestion groups don't carry.
  const checkedPayees: PayeeWithCount[] = payees.filter((p) => wizardChecked.has(p.id))
  const selectedPayees: PayeeWithCount[] = payees.filter((p) => selectedPayeeIds.has(p.id))
  const selectedCount = selectedPayeeIds.size
  const hiddenSelected = selectedCount - selectedInFiltered.length

  const tagOptions: TagOption[] = allTags.map((t) => ({
    id: t.id,
    name: t.name,
    color_slot: t.color_slot,
  }))

  async function handleBulkAddTags(tagIds: string[]) {
    if (tagIds.length === 0) return
    await bulkAddTags.mutateAsync({
      payeeIds: [...selectedPayeeIds],
      tagIds,
    })
    setShowBulkTagPicker(false)
  }

  async function handleCreateTagOption(name: string): Promise<TagOption> {
    const tag = await createTag.mutateAsync({ name })
    return { id: tag.id, name: tag.name, color_slot: tag.color_slot }
  }

  return (
    <div className={`payees-page ${selectedCount > 0 ? 'payees-page--with-bar' : ''}`}>
      <div className="payees-header surface surface--chrome">
        <div className="payees-title-wrap">
          <h1 className="payees-title">Payees</h1>
          {!isLoading && (
            <span className="payees-count">
              {totalPayees} payee{totalPayees !== 1 ? 's' : ''}
              {search.trim() ? ` · ${filtered.length} shown` : ''}
            </span>
          )}
        </div>
        <div className="payees-actions">
          <input
            type="search"
            className="payees-search"
            placeholder="Search…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button
            className="payees-btn payees-btn--primary"
            onClick={() => setShowCleanupModal(true)}
            disabled={fetchDuplicates.isPending}
            title="Find similar payees that may be duplicates"
          >
            {fetchDuplicates.isPending ? 'Scanning…' : 'Cleanup'}
          </button>
        </div>
      </div>

      {showCleanupModal && (
        <Dialog
          title="Payee Cleanup"
          onClose={() => setShowCleanupModal(false)}
          historyKey="payee-cleanup"
          className="payees-wizard"
          footer={
            <>
              <button className="payees-btn" onClick={() => setShowCleanupModal(false)}>
                Cancel
              </button>
              <button
                className="payees-btn payees-btn--primary"
                onClick={runCleanup}
                disabled={fetchDuplicates.isPending}
              >
                {fetchDuplicates.isPending ? 'Scanning…' : 'Find Duplicates'}
              </button>
            </>
          }
        >
          <div className="payees-wizard__body">
            <p className="payees-wizard__label">Find similar payees to merge</p>
            <p className="payees-wizard__sub">
              Names are compared with the bank's store numbers, reference codes and dates set aside,
              so postings that differ only there read as one payee.
            </p>
            <p className="payees-wizard__sub" style={{ marginTop: 'var(--spacing-md)' }}>
              Sensitivity:
            </p>
            <div className="payees-wizard__options">
              <button
                className={`payees-wizard__option ${sensitivity === 'strict' ? 'payees-wizard__option--selected' : ''}`}
                onClick={() => setSensitivity('strict')}
              >
                <strong>Strict</strong> — Only very similar names
              </button>
              <button
                className={`payees-wizard__option ${sensitivity === 'balanced' ? 'payees-wizard__option--selected' : ''}`}
                onClick={() => setSensitivity('balanced')}
              >
                <strong>Balanced</strong> — Recommended
              </button>
              <button
                className={`payees-wizard__option ${sensitivity === 'loose' ? 'payees-wizard__option--selected' : ''}`}
                onClick={() => setSensitivity('loose')}
              >
                <strong>Loose</strong> — More suggestions, some may be wrong
              </button>
            </div>
          </div>
        </Dialog>
      )}

      {showWizard && currentGroup && (
        <Dialog
          title={`Cleanup Wizard — ${wizardIdx + 1} of ${wizardGroups.length}`}
          onClose={() => setShowWizard(false)}
          historyKey="payee-wizard"
          className="payees-wizard"
          footer={
            <>
              <button className="payees-btn" onClick={prevWizard} disabled={wizardIdx === 0}>
                Back
              </button>
              <button className="payees-btn" onClick={nextWizard}>
                Skip
              </button>
              <button
                className="payees-btn payees-btn--primary"
                onClick={startWizardMerge}
                disabled={checkedPayees.length < 2 || mergePayee.isPending || updatePayee.isPending}
                title={checkedPayees.length < 2 ? 'Check at least 2 payees to merge' : undefined}
              >
                Merge {checkedPayees.length}…
              </button>
            </>
          }
        >
          <div className="payees-wizard__body">
            <p className="payees-wizard__label">
              These payees look similar: <strong>{currentGroup.label}</strong>
            </p>
            <p className="payees-wizard__sub">
              Uncheck any that don't belong, then merge the rest — you'll choose the surviving name
              next.
            </p>
            <div className="payees-wizard__options scroll-list">
              {currentGroup.payees.map((p) => {
                const isChecked = wizardChecked.has(p.id)
                const isPeeking = wizardPeekId === p.id
                return (
                  <div key={p.id} className="payees-wizard__candidate">
                    <label
                      className={`payees-wizard__option payees-wizard__option--check ${isChecked ? 'payees-wizard__option--selected' : ''}`}
                    >
                      <input
                        type="checkbox"
                        className="payees-checkbox"
                        checked={isChecked}
                        onChange={() =>
                          setWizardChecked((prev) => {
                            const next = new Set(prev)
                            if (next.has(p.id)) next.delete(p.id)
                            else next.add(p.id)
                            return next
                          })
                        }
                      />
                      <span>
                        <strong>"{p.name}"</strong>
                        {p.transaction_count !== undefined && (
                          <span className="payees-wizard__option-count">
                            ({p.transaction_count} txns)
                          </span>
                        )}
                      </span>
                      <button
                        type="button"
                        className={`payees-wizard__peek-btn ${isPeeking ? 'payees-wizard__peek-btn--open' : ''}`}
                        onClick={(e) => {
                          // Inside a <label>: without preventDefault the click
                          // would also toggle the checkbox.
                          e.preventDefault()
                          setWizardPeekId(isPeeking ? null : p.id)
                        }}
                        title={isPeeking ? 'Hide transactions' : 'Show recent transactions'}
                        aria-expanded={isPeeking}
                      >
                        {isPeeking ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    </label>
                    {isPeeking && budgetId && (
                      <PayeeTransactionPeek budgetId={budgetId} payeeId={p.id} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </Dialog>
      )}

      {showMergeModal && (
        <PayeeMergeModal
          payees={selectedPayees}
          allPayees={payees}
          onConfirm={executeMerge}
          onCancel={() => setShowMergeModal(false)}
          isPending={mergePayee.isPending || updatePayee.isPending}
        />
      )}

      {wizardMergePayees && (
        <PayeeMergeModal
          payees={wizardMergePayees}
          allPayees={payees}
          onConfirm={executeWizardMerge}
          onCancel={() => setWizardMergePayees(null)}
          isPending={mergePayee.isPending || updatePayee.isPending}
        />
      )}

      {isLoading ? (
        <div className="payees-empty">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="payees-empty">No payees found.</div>
      ) : (
        <div className="payees-table surface">
          <div className="payees-table__head">
            <div className="payees-table__checkbox-cell">
              <input
                ref={headerCheckboxRef}
                type="checkbox"
                className="payees-checkbox"
                checked={allFilteredSelected}
                onChange={handleSelectAllFiltered}
                aria-label="Select all visible payees"
              />
            </div>
            <span
              className={`payees-table__head-sortable ${sortColumn === 'name' ? 'payees-table__head-sortable--active' : ''}`}
              onClick={() => handleSort('name')}
            >
              Name
              {sortColumn === 'name' && <SortIcon size={12} className="payees-table__sort-icon" />}
            </span>
            <span>Tags</span>
            <span
              className={`payees-table__head-sortable ${sortColumn === 'transactions' ? 'payees-table__head-sortable--active' : ''}`}
              onClick={() => handleSort('transactions')}
              style={{ justifyContent: 'flex-end' }}
            >
              Transactions
              {sortColumn === 'transactions' && (
                <SortIcon size={12} className="payees-table__sort-icon" />
              )}
            </span>
            <span></span>
          </div>
          {filtered.map((p) => {
            const isSelected = selectedPayeeIds.has(p.id)
            const editing = editingId === p.id
            // What a pattern here is meant to claim — the name as typed plus
            // the recorded bank-name samples — and the payees it must not.
            const editNames = editing
              ? [editName.trim() || p.name, ...samplesFromLines(editMappings)]
              : []
            const editOthers = editing
              ? payees.filter((x) => x.id !== p.id && !x.transfer_account_id)
              : []
            const editCandidates = editing
              ? patternCandidates(editAiCandidates, suggestPayeeRegex(editNames))
              : []
            return (
              <div
                key={p.id}
                className={`payees-table__row ${editingId === p.id ? 'payees-table__row--editing' : ''} ${isSelected ? 'payees-table__row--selected' : ''}`}
              >
                <div className="payees-table__checkbox-cell">
                  <input
                    type="checkbox"
                    className="payees-checkbox"
                    checked={isSelected}
                    onChange={(e) =>
                      togglePayeeSelection(
                        p.id,
                        (e.nativeEvent as MouseEvent).shiftKey,
                        allOrderedIds
                      )
                    }
                    aria-label={`Select ${p.name}`}
                  />
                </div>
                <span className="payees-table__name">
                  {editingId === p.id ? (
                    <div className="payees-edit-fields">
                      <input
                        className="payees-edit-input"
                        value={editName}
                        autoFocus
                        onChange={(e) => setEditName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEdit(p.id)
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                        placeholder="Payee name"
                      />
                      <textarea
                        className="payees-edit-input payees-edit-input--mappings"
                        value={editMappings}
                        rows={2}
                        onChange={(e) => setEditMappings(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                        placeholder={
                          'Match samples (optional), one per line:\nNORTHWIND PAYSERV PAYROLL 250915 …'
                        }
                        aria-label="Match samples, one per line"
                      />
                      <span className="payees-edit-hint">
                        Bank names that should match this payee, one per line
                      </span>
                      <div className="payees-edit-pattern-row">
                        <input
                          className="payees-edit-input payees-edit-input--pattern"
                          value={editPattern}
                          onChange={(e) => setEditPattern(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') saveEdit(p.id)
                            if (e.key === 'Escape') setEditingId(null)
                          }}
                          placeholder="Match pattern (optional regex): ^ACH DEPOSIT PAYROLL"
                          spellCheck={false}
                        />
                        {aiStatus.data?.available === true && (
                          <button
                            type="button"
                            className="payees-btn payees-btn--sm payees-edit-ai-suggest"
                            onClick={() => {
                              void suggestRegex.mutateAsync(editNames).then((patterns) => {
                                setEditAiCandidates(patterns)
                                if (patterns.length === 0) {
                                  toast.error(NO_PATTERN_MESSAGE)
                                } else {
                                  setEditPattern((current) =>
                                    current.trim() ? current : patterns[0]
                                  )
                                }
                              })
                            }}
                            disabled={suggestRegex.isPending}
                            title="Ask the AI for patterns generalizing this payee's names"
                          >
                            <Sparkles size={12} aria-hidden />
                            {suggestRegex.isPending ? 'Thinking…' : 'AI'}
                          </button>
                        )}
                      </div>
                      <span className="payees-edit-hint">
                        Incoming names matching this regex map here, case-insensitive
                      </span>
                      <PatternCandidates
                        candidates={editCandidates}
                        value={editPattern.trim()}
                        names={editNames}
                        others={editOthers}
                        onPick={setEditPattern}
                      />
                      <PatternMatchPreview pattern={editPattern.trim()} names={editNames} />
                      <div className="payees-edit-btns">
                        <button
                          className="payees-btn payees-btn--sm payees-btn--primary"
                          onClick={() => saveEdit(p.id)}
                        >
                          Save
                        </button>
                        <button
                          className="payees-btn payees-btn--sm"
                          onClick={() => setEditingId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="payees-table__name-cell">
                      <span
                        className="payees-table__name-text"
                        onDoubleClick={() =>
                          startEdit(p.id, p.name, p.mapping_samples, p.match_pattern)
                        }
                        title="Double-click to rename"
                      >
                        {p.name}
                      </span>
                      {p.mapping_samples.length > 0 && (
                        <span
                          className="payees-table__mappings"
                          title={`Match samples: ${p.mapping_samples.join(' · ')}`}
                        >
                          {p.mapping_samples.join(' · ')}
                        </span>
                      )}
                      {p.match_pattern && (
                        <span
                          className="payees-table__pattern"
                          title={`Match pattern: ${p.match_pattern}`}
                        >
                          <Regex size={11} aria-hidden />
                          {p.match_pattern}
                        </span>
                      )}
                    </div>
                  )}
                </span>
                <span className="payees-table__tags">
                  {editingId === p.id ? (
                    <div className="payees-table__tags-list">
                      {(p.tags ?? []).map((tag) => (
                        <TagChip
                          key={tag.id}
                          name={tag.name}
                          colorSlot={tag.color_slot}
                          size="sm"
                          onRemove={() =>
                            setPayeeTags.mutate({
                              payeeId: p.id,
                              tagIds: (p.tags ?? [])
                                .filter((t) => t.id !== tag.id)
                                .map((t) => t.id),
                            })
                          }
                        />
                      ))}
                      <TagPicker
                        selectedTagIds={(p.tags ?? []).map((t) => t.id)}
                        tags={tagOptions}
                        onChange={(tagIds) => setPayeeTags.mutate({ payeeId: p.id, tagIds })}
                        onCreateTag={handleCreateTagOption}
                        allowCreate
                        triggerLabel="+ Tag"
                        ghost
                      />
                    </div>
                  ) : p.tags && p.tags.length > 0 ? (
                    <div className="payees-table__tags-list">
                      {p.tags.slice(0, 2).map((tag) => (
                        <TagChip
                          key={tag.id}
                          name={tag.name}
                          colorSlot={tag.color_slot}
                          size="sm"
                        />
                      ))}
                      {p.tags.length > 2 && (
                        <span
                          className="payees-table__tags-overflow"
                          title={p.tags
                            .slice(2)
                            .map((t) => t.name)
                            .join(', ')}
                        >
                          +{p.tags.length - 2}
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="payees-table__no-tags">—</span>
                  )}
                </span>
                <span className="payees-table__count">{p.transaction_count}</span>
                <span className="payees-table__actions">
                  {editingId === p.id ? null : (
                    <>
                      <button
                        className="payees-btn payees-btn--sm"
                        onClick={() => startEdit(p.id, p.name, p.mapping_samples, p.match_pattern)}
                      >
                        Edit
                      </button>
                      <button
                        className="payees-btn payees-btn--sm payees-btn--danger"
                        onClick={() => handleDelete(p.id, p.name)}
                        disabled={deletePayee.isPending}
                      >
                        Delete
                      </button>
                    </>
                  )}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {selectedCount > 0 && (
        <FloatingSelectionBar
          label={`${selectedCount} payee${selectedCount !== 1 ? 's' : ''} selected`}
          sublabel={hiddenSelected > 0 ? `(${hiddenSelected} hidden by search)` : undefined}
          onClose={clearPayeeSelection}
        >
          <div className="payees-bulk-tag-wrapper">
            <FloatingSelectionBar.Button onClick={() => setShowBulkTagPicker(!showBulkTagPicker)}>
              <Tag size={14} />
              Tag
            </FloatingSelectionBar.Button>
            {showBulkTagPicker && (
              <div className="payees-bulk-tag-picker">
                <TagPicker
                  selectedTagIds={[]}
                  tags={tagOptions}
                  onChange={handleBulkAddTags}
                  onCreateTag={handleCreateTagOption}
                  allowCreate
                  triggerLabel="Select tags to add"
                />
              </div>
            )}
          </div>
          <FloatingSelectionBar.Button
            onClick={() => setShowMergeModal(true)}
            disabled={selectedCount < 2}
            title={
              selectedCount < 2
                ? 'Select at least 2 payees to merge'
                : `Merge ${selectedCount} payees`
            }
          >
            <GitMerge size={14} />
            Merge
          </FloatingSelectionBar.Button>
        </FloatingSelectionBar>
      )}
    </div>
  )
}
