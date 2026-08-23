import { parseApiDecimal } from '../../utils/money'
import { useState } from 'react'
import { Undo2, Package, RefreshCw, Trash2, Edit3, Plus, CheckCircle, FileUp, GitMerge } from 'lucide-react'
import { useAppStore } from '../../stores/appStore'
import { useChanges, useUndoChange, invalidateAfterUndo, type Change } from '../../api/changes'
import { useQueryClient } from '@tanstack/react-query'
import { useFormatters } from '../../hooks/useFormatters'
import toast from 'react-hot-toast'
import { groupChanges } from './groupChanges'
import './ActivityPage.css'

const PAGE_SIZE = 50

export function ActivityPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const qc = useQueryClient()
  const { formatDateTime } = useFormatters()
  const [offset, setOffset] = useState(0)

  const { data, isLoading, error } = useChanges(budgetId, PAGE_SIZE, offset)
  const undoChange = useUndoChange(budgetId ?? '')

  if (!budgetId) {
    return (
      <div className="activity-page">
        <p className="activity-page__empty">Select a budget to view activity.</p>
      </div>
    )
  }

  const changes = data?.changes ?? []
  const total = data?.total ?? 0
  const hasMore = offset + changes.length < total

  const grouped = groupChanges(changes)

  async function handleUndo(changeId: string) {
    try {
      await undoChange.mutateAsync({ changeId })
      invalidateAfterUndo(qc, budgetId!)
      toast.success('Undone')
    } catch {
      // Error toast handled by the hook
    }
  }

  return (
    <div className="activity-page">
      <div className="activity-page__header">
        <h1 className="activity-page__title">Activity</h1>
        <span className="activity-page__count">{total} changes</span>
      </div>

      {isLoading && <p className="activity-page__loading">Loading…</p>}
      {error && <p className="activity-page__error">Could not load activity.</p>}

      {!isLoading && changes.length === 0 && (
        <p className="activity-page__empty">No changes recorded yet.</p>
      )}

      <div className="activity-list">
        {grouped.map((group, i) => (
          <div key={group.batchId ?? `single-${i}`} className="activity-group">
            {group.changes.length > 1 && (
              <div className="activity-group__header">
                <Package size={14} />
                <span>Batch of {group.changes.length}</span>
              </div>
            )}
            {group.changes.map((change) => (
              <ChangeCard
                key={change.id}
                change={change}
                formatDateTime={formatDateTime}
                onUndo={() => handleUndo(change.id)}
                isUndoing={undoChange.isPending}
              />
            ))}
          </div>
        ))}
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

interface ChangeCardProps {
  change: Change
  formatDateTime: (date: string) => string
  onUndo: () => void
  isUndoing: boolean
}

function ChangeCard({ change, formatDateTime, onUndo, isUndoing }: ChangeCardProps) {
  const icon = actionIcon(change.action)
  const entityLabel = entityTypeLabel(change.entity_type)
  const actionLabel = actionTypeLabel(change.action)
  const isUndone = !!change.undone_at

  // Show a summary of what changed
  let summary = ''
  if (change.action === 'create' || change.action === 'import') {
    summary = summarizeAfter(change)
  } else if (change.action === 'delete') {
    summary = summarizeBefore(change)
  } else if (change.action === 'update' || change.action === 'approve') {
    summary = summarizeUpdate(change)
  } else if (change.action === 'merge') {
    summary = 'Merged into another'
  }

  return (
    <div className={`change-card ${isUndone ? 'change-card--undone' : ''}`}>
      <div className="change-card__icon">{icon}</div>
      <div className="change-card__content">
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
    default:
      return <RefreshCw size={14} />
  }
}

function entityTypeLabel(entityType: string): string {
  switch (entityType) {
    case 'transaction':
      return 'transaction'
    case 'payee':
      return 'payee'
    case 'category':
      return 'category'
    case 'category_group':
      return 'category group'
    case 'assignment':
      return 'assignment'
    default:
      return entityType
  }
}

function actionTypeLabel(action: string): string {
  switch (action) {
    case 'create':
      return 'Created'
    case 'update':
      return 'Updated'
    case 'delete':
      return 'Deleted'
    case 'approve':
      return 'Approved'
    case 'import':
      return 'Imported'
    case 'merge':
      return 'Merged'
    default:
      return action
  }
}

function summarizeAfter(change: Change): string {
  const after = change.after
  if (!after) return ''

  if (change.entity_type === 'transaction') {
    const amount = after.amount as string | undefined
    const memo = after.memo as string | undefined
    if (amount) {
      const amtNum = parseApiDecimal(amount)
      const formatted = Math.abs(amtNum).toFixed(2)
      return `${amtNum < 0 ? '-' : '+'}$${formatted}${memo ? ` – ${memo}` : ''}`
    }
  }

  if (change.entity_type === 'payee') {
    return (after.name as string) ?? ''
  }

  if (change.entity_type === 'category') {
    return (after.name as string) ?? ''
  }

  if (change.entity_type === 'assignment') {
    const assigned = after.assigned as string | undefined
    if (assigned) {
      return `Assigned $${parseApiDecimal(assigned).toFixed(2)}`
    }
  }

  return ''
}

function summarizeBefore(change: Change): string {
  const before = change.before
  if (!before) return ''

  if (change.entity_type === 'transaction') {
    const amount = before.amount as string | undefined
    const memo = before.memo as string | undefined
    if (amount) {
      const amtNum = parseApiDecimal(amount)
      const formatted = Math.abs(amtNum).toFixed(2)
      return `${amtNum < 0 ? '-' : '+'}$${formatted}${memo ? ` – ${memo}` : ''}`
    }
  }

  if (change.entity_type === 'payee') {
    return (before.name as string) ?? ''
  }

  if (change.entity_type === 'category') {
    return (before.name as string) ?? ''
  }

  return ''
}

function summarizeUpdate(change: Change): string {
  const before = change.before ?? {}
  const after = change.after ?? {}

  // Find fields that changed
  const changed: string[] = []
  for (const key of Object.keys(after)) {
    if (key.startsWith('_')) continue
    const b = before[key]
    const a = after[key]
    if (String(b) !== String(a)) {
      changed.push(key)
    }
  }

  if (changed.length === 0) return ''
  if (changed.length === 1) {
    const field = changed[0]
    if (field === 'approved') return 'Marked approved'
    if (field === 'cleared') return `Cleared: ${after.cleared}`
    if (field === 'amount') {
      const a = parseApiDecimal(after.amount as string)
      return `Amount → ${a < 0 ? '-' : '+'}$${Math.abs(a).toFixed(2)}`
    }
    if (field === 'name') return `Renamed to "${after.name}"`
    if (field === 'assigned') {
      return `Assigned → $${parseApiDecimal(after.assigned as string).toFixed(2)}`
    }
    return `Changed ${field}`
  }
  return `Changed ${changed.length} fields`
}
