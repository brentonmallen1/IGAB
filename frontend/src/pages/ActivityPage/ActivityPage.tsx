import { Fragment, useState } from 'react'
import {
  Undo2,
  Redo2,
  Package,
  RefreshCw,
  Trash2,
  Edit3,
  Plus,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  FileUp,
  GitMerge,
  History,
  Archive,
  ArchiveRestore,
} from 'lucide-react'
import { useAppStore } from '../../stores/appStore'
import {
  useChanges,
  useUndoBatch,
  useUndoChange,
  useUndoNewer,
  invalidateAfterUndo,
  type Change,
} from '../../api/changes'
import { useQueryClient } from '@tanstack/react-query'
import { useFormatters } from '../../hooks/useFormatters'
import { confirmAsync } from '../../stores/confirmStore'
import toast from 'react-hot-toast'
import { groupChanges, redoHeadId, summarizeBatch } from './groupChanges'
import { useUndoRedo } from '../../hooks/useUndoRedo'
import { actionTypeLabel, entityTypeLabel } from './changeLabels'
import { diffRows, summarizeChange, type Names } from './changeDetails'
import './ActivityPage.css'

const PAGE_SIZE = 50

export function ActivityPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const qc = useQueryClient()
  const { formatDateTime } = useFormatters()
  const [offset, setOffset] = useState(0)

  const { data, isLoading, error } = useChanges(budgetId, PAGE_SIZE, offset)
  const undoChange = useUndoChange(budgetId ?? '')
  const undoBatch = useUndoBatch(budgetId ?? '')
  const undoNewer = useUndoNewer(budgetId ?? '')
  // One redo for every way of asking — same hook as ⌘⇧Z and the header.
  const { redo } = useUndoRedo()
  // Batches collapse to one line; a user who wants the detail asks for it.
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  // Index of the group the hovered line sits directly below. Everything
  // above it is what "revert to here" would take.
  const [hoveredLine, setHoveredLine] = useState<number | null>(null)

  if (!budgetId) {
    return (
      <div className="activity-page">
        <p className="activity-page__empty">Select a budget to view activity.</p>
      </div>
    )
  }

  const changes = data?.changes ?? []
  const total = data?.total ?? 0
  const names = data?.names ?? {}
  const hasMore = offset + changes.length < total

  const grouped = groupChanges(changes)
  // Where redo would land right now — the only row that gets the button.
  const redoHead = redoHeadId(changes, offset)

  async function handleUndo(changeId: string) {
    try {
      await undoChange.mutateAsync({ changeId })
      invalidateAfterUndo(qc, budgetId!)
      toast.success('Undone')
    } catch {
      // Error toast handled by the hook
    }
  }

  async function handleUndoBatch(batchId: string, label: string) {
    try {
      const result = await undoBatch.mutateAsync({ batchId })
      invalidateAfterUndo(qc, budgetId!)
      // The server undoes the whole batch even when this page is showing
      // only part of it, so the count comes back from the server.
      toast.success(`Undid ${label.toLowerCase()} — ${result.undone_change_ids.length} changes`)
    } catch {
      // Error toast handled by the hook
    }
  }

  /**
   * Revert to the line drawn under `groupIndex`: everything above it goes.
   *
   * The count is asked for first, with dry_run, so the number in the prompt
   * is produced by the same query that does the work — and so it can include
   * changes newer than the page currently being looked at.
   */
  async function handleRevertTo(groupIndex: number) {
    const below = grouped[groupIndex + 1]
    if (!below) return
    const anchorId = below.changes[0].id
    let count: number
    try {
      const preview = await undoNewer.mutateAsync({ changeId: anchorId, dryRun: true })
      count = preview.undone_change_ids.length
    } catch {
      toast.error('Could not work out what reverting here would undo')
      return
    }
    if (count === 0) {
      toast('Nothing to revert above this point')
      return
    }
    const ok = await confirmAsync({
      title: `Undo the ${count} change${count === 1 ? '' : 's'} above this line?`,
      message: 'Everything below the line stays exactly as it is.',
      confirmLabel: `Undo ${count} change${count === 1 ? '' : 's'}`,
      destructive: true,
    })
    if (!ok) return
    try {
      const result = await undoNewer.mutateAsync({ changeId: anchorId })
      invalidateAfterUndo(qc, budgetId!)
      setHoveredLine(null)
      toast.success(`Reverted ${result.undone_change_ids.length} changes`)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      const message = typeof detail === 'string' ? detail : detail?.message
      toast.error(message ?? 'Could not revert to this point')
    }
  }

  function toggleExpanded(batchId: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(batchId)) next.delete(batchId)
      else next.add(batchId)
      return next
    })
  }

  return (
    <div className="activity-page page-fill">
      <div className="activity-page__header">
        <h1 className="activity-page__title">Activity</h1>
        <span className="activity-page__count">{total} changes</span>
      </div>

      {isLoading && <p className="activity-page__loading">Loading…</p>}
      {error && <p className="activity-page__error">Could not load activity.</p>}

      {!isLoading && changes.length === 0 && (
        <p className="activity-page__empty">No changes recorded yet.</p>
      )}

      <div className="activity-list surface scroll-fill">
        {grouped.map((group, i) => {
          const isBatch = group.changes.length > 1 && group.batchId !== null
          const isOpen = group.batchId !== null && expanded.has(group.batchId)
          return (
            <Fragment key={group.batchId ?? `single-${i}`}>
              <div
                className={`activity-group ${
                  hoveredLine !== null && i <= hoveredLine ? 'activity-group--reverting' : ''
                }`}
              >
                {isBatch && (
                  <BatchHeader
                    group={group}
                    isOpen={isOpen}
                    formatDateTime={formatDateTime}
                    onToggle={() => toggleExpanded(group.batchId!)}
                    onUndo={() => handleUndoBatch(group.batchId!, summarizeBatch(group.changes))}
                    isUndoing={undoBatch.isPending}
                    showRedo={group.changes.some((c) => c.id === redoHead)}
                    onRedo={redo}
                  />
                )}
                {(!isBatch || isOpen) &&
                  group.changes.map((change) => (
                    <ChangeCard
                      key={change.id}
                      change={change}
                      names={names}
                      formatDateTime={formatDateTime}
                      onUndo={() => handleUndo(change.id)}
                      isUndoing={undoChange.isPending}
                      showRedo={!isBatch && change.id === redoHead}
                      onRedo={redo}
                    />
                  ))}
              </div>
              {/* The revert point rests BETWEEN two entries, so there is
                  never a question of whether the one you clicked is included:
                  everything above the line goes, everything below stays. */}
              {i < grouped.length - 1 && (
                <button
                  type="button"
                  className="activity-revert-line"
                  onMouseEnter={() => setHoveredLine(i)}
                  onMouseLeave={() => setHoveredLine(null)}
                  onFocus={() => setHoveredLine(i)}
                  onBlur={() => setHoveredLine(null)}
                  onClick={() => handleRevertTo(i)}
                  disabled={undoNewer.isPending}
                  title="Undo everything above this line"
                >
                  <span className="activity-revert-line__rule" />
                  <span className="activity-revert-line__label">
                    <History size={12} />
                    Revert to here
                  </span>
                  <span className="activity-revert-line__rule" />
                </button>
              )}
            </Fragment>
          )
        })}
      </div>

      {(offset > 0 || hasMore) && (
        <div className="activity-page__pagination">
          <button
            className="activity-page__page-btn"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            ← Newer
          </button>
          <span className="activity-page__page-info">
            {offset + 1}–{Math.min(offset + changes.length, total)} of {total}
          </span>
          <button
            className="activity-page__page-btn"
            disabled={!hasMore}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Older →
          </button>
        </div>
      )}
    </div>
  )
}

interface BatchHeaderProps {
  group: { batchId: string | null; changes: Change[] }
  isOpen: boolean
  formatDateTime: (date: string) => string
  onToggle: () => void
  onUndo: () => void
  isUndoing: boolean
  /** True only when this batch holds the current redo head. */
  showRedo: boolean
  onRedo: () => void
}

/**
 * One line for a batch — a bulk assign of forty categories used to be forty
 * cards, which buried everything else that happened that day.
 *
 * The count is "on this page": a batch can straddle the page boundary. Undo
 * takes the whole batch regardless, which is why the toast reports the
 * server's number rather than this one.
 */
function BatchHeader({
  group,
  isOpen,
  formatDateTime,
  onToggle,
  onUndo,
  isUndoing,
  showRedo,
  onRedo,
}: BatchHeaderProps) {
  const allUndone = group.changes.every((c) => c.undone_at)
  const newest = group.changes[0]

  return (
    <div className={`batch-header ${allUndone ? 'batch-header--undone' : ''}`}>
      <button
        type="button"
        className="batch-header__toggle"
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Package size={14} />
        <span className="batch-header__summary">{summarizeBatch(group.changes)}</span>
      </button>
      <span className="batch-header__actor">
        {newest.user_display_name ??
          (newest.source === 'ai' ? 'AI' : newest.source === 'manual' ? '' : newest.source)}
      </span>
      <span className="batch-header__time">{formatDateTime(newest.created_at)}</span>
      {allUndone ? (
        <>
          <span className="batch-header__badge">Undone</span>
          {showRedo && (
            <button
              type="button"
              className="change-card__undo"
              onClick={onRedo}
              title="Redo this whole batch"
            >
              <Redo2 size={14} />
            </button>
          )}
        </>
      ) : (
        <button
          type="button"
          className="change-card__undo"
          onClick={onUndo}
          disabled={isUndoing}
          title="Undo this whole batch"
        >
          <Undo2 size={14} />
        </button>
      )}
    </div>
  )
}

interface ChangeCardProps {
  change: Change
  names: Names
  formatDateTime: (date: string) => string
  onUndo: () => void
  isUndoing: boolean
  /** True only when this row is the current redo head. */
  showRedo: boolean
  onRedo: () => void
}

function ChangeCard({
  change,
  names,
  formatDateTime,
  onUndo,
  isUndoing,
  showRedo,
  onRedo,
}: ChangeCardProps) {
  const icon = actionIcon(change.action)
  const entityLabel = entityTypeLabel(change.entity_type, change.action)
  const actionLabel = actionTypeLabel(change.action)
  const isUndone = !!change.undone_at
  const summary = summarizeChange(change, names)
  const rows = diffRows(change, names)
  // Tap the row to see the before → after detail. A tap, not a hover: the
  // phone is an installed PWA where hover does not exist.
  const [open, setOpen] = useState(false)

  return (
    <div className={`change-card ${isUndone ? 'change-card--undone' : ''}`}>
      <div className="change-card__icon">{icon}</div>
      <div className="change-card__content">
        <button
          type="button"
          className="change-card__reveal"
          onClick={() => setOpen((o) => !o)}
          disabled={rows.length === 0}
          aria-expanded={open}
          title={rows.length > 0 && !open ? 'Show what changed' : undefined}
        >
          <div className="change-card__header">
            <span className="change-card__action">
              {actionLabel} {entityLabel}
            </span>
            {/* Who did it — matters once a budget is shared. System/AI changes
                carry no user; show the source instead. */}
            <span className="change-card__actor">
              {change.user_display_name ??
                (change.source === 'ai' ? 'AI' : change.source === 'manual' ? '' : change.source)}
            </span>
            <span className="change-card__time">{formatDateTime(change.created_at)}</span>
          </div>
          {summary && <div className="change-card__summary">{summary}</div>}
        </button>
        {open && rows.length > 0 && (
          <dl className="change-card__diff">
            {rows.map((row, i) => (
              <div className="change-card__diff-row" key={`${row.label}-${i}`}>
                <dt className="change-card__diff-label">{row.label}</dt>
                <dd className="change-card__diff-values">
                  {row.before !== null && (
                    <span className="change-card__diff-before">{row.before}</span>
                  )}
                  {row.before !== null && row.after !== null && (
                    <span className="change-card__diff-arrow" aria-hidden>
                      →
                    </span>
                  )}
                  {row.after !== null && (
                    <span className="change-card__diff-after">{row.after}</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {isUndone && <div className="change-card__undone-badge">Undone</div>}
      </div>
      {!isUndone && (
        <button
          className="change-card__undo"
          onClick={onUndo}
          disabled={isUndoing}
          title="Undo this change"
        >
          <Undo2 size={14} />
        </button>
      )}
      {isUndone && showRedo && (
        <button className="change-card__undo" onClick={onRedo} title="Redo this change">
          <Redo2 size={14} />
        </button>
      )}
    </div>
  )
}

function actionIcon(action: string) {
  switch (action) {
    case 'create':
      return <Plus size={14} />
    case 'update':
      return <Edit3 size={14} />
    case 'delete':
      return <Trash2 size={14} />
    case 'approve':
      return <CheckCircle size={14} />
    case 'import':
      return <FileUp size={14} />
    case 'merge':
      return <GitMerge size={14} />
    case 'archive':
      return <Archive size={14} />
    case 'unarchive':
      return <ArchiveRestore size={14} />
    default:
      return <RefreshCw size={14} />
  }
}
