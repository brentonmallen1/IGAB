import { useState, useRef, useEffect } from 'react'
import { GitMerge, X } from 'lucide-react'
import type { PayeeWithCount } from '../../../api/payees'
import './PayeeMergeModal.css'

export interface MergeConfig {
  targetId: string
  addToMappingSamples: boolean
  customName?: string
}

interface Props {
  payees: PayeeWithCount[]
  onConfirm: (config: MergeConfig) => void
  onCancel: () => void
  isPending: boolean
}

function deduplicateSamples(parts: (string | null | undefined)[]): string {
  const seen = new Set<string>()
  const result: string[] = []
  for (const part of parts) {
    if (!part) continue
    for (const sample of part.split(',')) {
      const trimmed = sample.trim()
      if (trimmed && !seen.has(trimmed.toLowerCase())) {
        seen.add(trimmed.toLowerCase())
        result.push(trimmed)
      }
    }
  }
  return result.join(', ')
}

export function PayeeMergeModal({ payees, onConfirm, onCancel, isPending }: Props) {
  const sorted = [...payees].sort((a, b) => b.transaction_count - a.transaction_count)
  const [targetId, setTargetId] = useState(sorted[0]?.id ?? '')
  const [useCustomName, setUseCustomName] = useState(false)
  const [customName, setCustomName] = useState('')
  const [addToMappingSamples, setAddToMappingSamples] = useState(true)
  const customInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (useCustomName) customInputRef.current?.focus()
  }, [useCustomName])

  const target = payees.find((p) => p.id === targetId)
  const sources = useCustomName ? payees : payees.filter((p) => p.id !== targetId)
  const totalTransactions = payees.reduce((sum, p) => sum + p.transaction_count, 0)
  const survivingName = useCustomName ? (customName.trim() || '…') : target?.name

  const previewMappings = addToMappingSamples
    ? deduplicateSamples([
        useCustomName ? null : target?.mapping_samples,
        ...sources.map((p) => p.name),
        ...sources.map((p) => p.mapping_samples),
      ])
    : useCustomName ? null : (target?.mapping_samples ?? '')

  const canConfirm = !isPending && (useCustomName ? customName.trim().length > 0 : !!targetId)

  function handleConfirm() {
    if (useCustomName) {
      onConfirm({ targetId: sorted[0].id, addToMappingSamples, customName: customName.trim() })
    } else {
      onConfirm({ targetId, addToMappingSamples })
    }
  }

  return (
    <div className="pmerge-overlay" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="pmerge-modal" role="dialog" aria-modal aria-labelledby="pmerge-title">
        <div className="pmerge-modal__header">
          <span id="pmerge-title" className="pmerge-modal__title">
            <GitMerge size={14} />
            Merge {payees.length} Payees
          </span>
          <button className="pmerge-modal__close" onClick={onCancel} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        <div className="pmerge-modal__body">
          <p className="pmerge-section-label">Keep this name</p>
          <div className="pmerge-options">
            {sorted.map((p) => (
              <label key={p.id} className={`pmerge-option ${!useCustomName && targetId === p.id ? 'pmerge-option--selected' : ''}`}>
                <input
                  type="radio"
                  name="target"
                  value={p.id}
                  checked={!useCustomName && targetId === p.id}
                  onChange={() => { setTargetId(p.id); setUseCustomName(false) }}
                />
                <span className="pmerge-option__name">{p.name}</span>
                <span className="pmerge-option__count">{p.transaction_count} txn</span>
              </label>
            ))}
            <label className={`pmerge-option pmerge-option--custom ${useCustomName ? 'pmerge-option--selected' : ''}`}>
              <input
                type="radio"
                name="target"
                value="__custom__"
                checked={useCustomName}
                onChange={() => setUseCustomName(true)}
              />
              {useCustomName ? (
                <input
                  ref={customInputRef}
                  className="pmerge-custom-input"
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="Enter a new name…"
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className="pmerge-option__name pmerge-option__name--placeholder">Enter a custom name…</span>
              )}
            </label>
          </div>

          <div className="pmerge-divider" />

          <label className="pmerge-checkbox-row">
            <input
              type="checkbox"
              checked={addToMappingSamples}
              onChange={(e) => setAddToMappingSamples(e.target.checked)}
            />
            <span>Add absorbed names to fuzzy match list</span>
          </label>
          <p className="pmerge-hint">
            Future imports with these names will automatically match the surviving payee.
          </p>

          {addToMappingSamples && (
            <div className="pmerge-preview">
              <span className="pmerge-preview__label">Match samples after merge:</span>
              <span className="pmerge-preview__value">
                {previewMappings || <em>none</em>}
              </span>
            </div>
          )}

          <div className="pmerge-summary">
            <span className="pmerge-summary__surviving">
              Surviving: <strong>{survivingName}</strong>
            </span>
            <span className="pmerge-summary__detail">
              {sources.length} payee{sources.length !== 1 ? 's' : ''} absorbed · {totalTransactions} transactions reassigned
            </span>
          </div>
        </div>

        <div className="pmerge-modal__footer">
          <button className="pmerge-btn pmerge-btn--cancel" onClick={onCancel} disabled={isPending}>
            Cancel
          </button>
          <button
            className="pmerge-btn pmerge-btn--confirm"
            onClick={handleConfirm}
            disabled={!canConfirm}
          >
            {isPending ? 'Merging…' : `Merge ${payees.length} Payees`}
          </button>
        </div>
      </div>
    </div>
  )
}
