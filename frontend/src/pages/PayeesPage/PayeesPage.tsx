import { useState } from 'react'
import { useAppStore } from '../../stores/appStore'
import { usePayees, useUpdatePayee, useDeletePayee, useMergePayee } from '../../api/payees'
import { usePayeeCleanupSuggestions, type PayeeCleanupGroup } from '../../api/ai'
import './PayeesPage.css'

export function PayeesPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: payees = [], isLoading } = usePayees(budgetId)
  const updatePayee = useUpdatePayee(budgetId)
  const deletePayee = useDeletePayee(budgetId)
  const mergePayee = useMergePayee(budgetId)
  const cleanup = usePayeeCleanupSuggestions(budgetId)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [mergeSource, setMergeSource] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [showWizard, setShowWizard] = useState(false)
  const [wizardGroups, setWizardGroups] = useState<PayeeCleanupGroup[]>([])
  const [wizardIdx, setWizardIdx] = useState(0)

  if (!budgetId) {
    return <div className="payees-page"><div className="payees-empty">Select a budget to manage payees.</div></div>
  }

  const filtered = payees.filter(
    (p) => !p.transfer_account_id && p.name.toLowerCase().includes(search.toLowerCase()),
  )

  function startEdit(id: string, name: string) {
    setEditingId(id)
    setEditName(name)
  }

  async function saveEdit(id: string) {
    if (editName.trim()) await updatePayee.mutateAsync({ id, name: editName.trim() })
    setEditingId(null)
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete payee "${name}"? Transactions will have no payee.`)) return
    await deletePayee.mutateAsync(id)
  }

  async function handleMerge(sourceId: string, targetId: string) {
    await mergePayee.mutateAsync({ sourceId, targetId })
    setMergeSource(null)
  }

  async function runCleanup() {
    const result = await cleanup.refetch()
    if (result.data && result.data.length > 0) {
      setWizardGroups(result.data)
      setWizardIdx(0)
      setShowWizard(true)
    } else {
      alert('No duplicate payees found.')
    }
  }

  async function acceptWizardGroup(group: PayeeCleanupGroup, keepId: string) {
    const toMerge = group.payees.filter((p) => p.id !== keepId)
    for (const p of toMerge) {
      await mergePayee.mutateAsync({ sourceId: p.id, targetId: keepId })
    }
    nextWizard()
  }

  function nextWizard() {
    if (wizardIdx + 1 >= wizardGroups.length) {
      setShowWizard(false)
    } else {
      setWizardIdx(wizardIdx + 1)
    }
  }

  const currentGroup = wizardGroups[wizardIdx]

  return (
    <div className="payees-page">
      <div className="payees-header">
        <h1 className="payees-title">Payees</h1>
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
            onClick={runCleanup}
            disabled={cleanup.isFetching}
          >
            {cleanup.isFetching ? 'Scanning…' : 'AI Cleanup'}
          </button>
        </div>
      </div>

      {showWizard && currentGroup && (
        <div className="payees-wizard-overlay" onClick={(e) => e.target === e.currentTarget && setShowWizard(false)}>
          <div className="payees-wizard">
            <div className="payees-wizard__header">
              <span>Cleanup Wizard ({wizardIdx + 1} / {wizardGroups.length})</span>
              <button className="payees-wizard__close" onClick={() => setShowWizard(false)}>×</button>
            </div>
            <div className="payees-wizard__body">
              <p className="payees-wizard__label">
                These payees look like the same vendor: <strong>{currentGroup.canonical}</strong>
              </p>
              <p className="payees-wizard__sub">Select which name to keep — the others will be merged into it.</p>
              <div className="payees-wizard__options">
                {currentGroup.payees.map((p) => (
                  <button
                    key={p.id}
                    className="payees-wizard__option"
                    onClick={() => acceptWizardGroup(currentGroup, p.id)}
                    disabled={mergePayee.isPending}
                  >
                    Keep <strong>"{p.name}"</strong>
                  </button>
                ))}
              </div>
            </div>
            <div className="payees-wizard__footer">
              <button className="payees-btn" onClick={nextWizard}>Skip</button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="payees-empty">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="payees-empty">No payees found.</div>
      ) : (
        <div className="payees-table">
          <div className="payees-table__head">
            <span>Name</span>
            <span>Transactions</span>
            <span></span>
          </div>
          {filtered.map((p) => (
            <div key={p.id} className="payees-table__row">
              <span className="payees-table__name">
                {editingId === p.id ? (
                  <input
                    className="payees-edit-input"
                    value={editName}
                    autoFocus
                    onChange={(e) => setEditName(e.target.value)}
                    onBlur={() => saveEdit(p.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit(p.id)
                      if (e.key === 'Escape') setEditingId(null)
                    }}
                  />
                ) : (
                  <span
                    className="payees-table__name-text"
                    onDoubleClick={() => startEdit(p.id, p.name)}
                    title="Double-click to rename"
                  >
                    {p.name}
                  </span>
                )}
              </span>
              <span className="payees-table__count">{p.transaction_count}</span>
              <span className="payees-table__actions">
                {mergeSource === p.id ? (
                  <span className="payees-merge-hint">Click another payee's Merge → to merge into it</span>
                ) : mergeSource ? (
                  <button
                    className="payees-btn payees-btn--sm payees-btn--primary"
                    onClick={() => handleMerge(mergeSource, p.id)}
                    disabled={mergePayee.isPending}
                  >
                    Merge →
                  </button>
                ) : (
                  <>
                    <button
                      className="payees-btn payees-btn--sm"
                      onClick={() => startEdit(p.id, p.name)}
                    >
                      Rename
                    </button>
                    <button
                      className="payees-btn payees-btn--sm"
                      onClick={() => setMergeSource(p.id)}
                    >
                      Merge
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
          ))}
        </div>
      )}
      {mergeSource && (
        <div className="payees-merge-bar">
          Merging "{payees.find((p) => p.id === mergeSource)?.name}" — click "Merge →" on the target payee
          <button className="payees-btn payees-btn--sm" onClick={() => setMergeSource(null)}>Cancel</button>
        </div>
      )}
    </div>
  )
}
