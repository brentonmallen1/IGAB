import { useState, useRef, useEffect, useMemo } from 'react'
import { Check, GitMerge, Regex, Sparkles, X } from 'lucide-react'
import type { PayeeWithCount } from '../../../api/payees'
import { useAIStatus, useNormalizePayee } from '../../../api/ai'
import { useAppStore } from '../../../stores/appStore'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import { suggestPayeeRegex, testPattern } from '../../../utils/payeeRegex'
import './PayeeMergeModal.css'

export interface MergeConfig {
  targetId: string
  addToMappingSamples: boolean
  customName?: string
  matchPattern?: string
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
  const [usePattern, setUsePattern] = useState(false)
  const [pattern, setPattern] = useState('')
  const trapRef = useFocusTrap<HTMLDivElement>(onCancel)
  const customInputRef = useRef<HTMLInputElement>(null)
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const aiAvailable = useAIStatus().data?.available === true
  const normalizePayee = useNormalizePayee(budgetId ?? '')

  // AI cleanup of the surviving name: feeds the messiest raw name through
  // normalize-payee and drops the result into the custom-name input.
  async function handleNormalize() {
    const source = customName.trim() || sorted[0]?.name
    if (!source) return
    const normalized = await normalizePayee.mutateAsync(source)
    setUseCustomName(true)
    setCustomName(normalized)
  }

  useEffect(() => {
    if (useCustomName) customInputRef.current?.focus()
  }, [useCustomName])

  // Every raw name this merge represents: payee names plus their recorded
  // bank-name samples. Both feed the suggestion and the live match preview.
  const rawNames = useMemo(() => {
    const names = payees.flatMap((p) => [
      p.name,
      ...(p.mapping_samples?.split(',').map((s) => s.trim()) ?? []),
    ])
    return [...new Set(names.filter(Boolean))]
  }, [payees])

  const suggestion = useMemo(() => suggestPayeeRegex(rawNames), [rawNames])

  function togglePattern() {
    setUsePattern((on) => {
      if (!on && !pattern && suggestion) setPattern(suggestion)
      return !on
    })
  }

  const trimmedPattern = pattern.trim()
  const patternResults = trimmedPattern
    ? rawNames.map((name) => ({ name, matches: testPattern(trimmedPattern, name) }))
    : []
  const patternInvalid = patternResults.some((r) => r.matches === null)

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

  const patternOk = !usePattern || (trimmedPattern.length > 0 && !patternInvalid)
  const canConfirm =
    !isPending && patternOk && (useCustomName ? customName.trim().length > 0 : !!targetId)

  function handleConfirm() {
    const matchPattern = usePattern && trimmedPattern ? trimmedPattern : undefined
    if (useCustomName) {
      onConfirm({
        targetId: sorted[0].id,
        addToMappingSamples,
        customName: customName.trim(),
        matchPattern,
      })
    } else {
      onConfirm({ targetId, addToMappingSamples, matchPattern })
    }
  }

  return (
    <div className="pmerge-overlay" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div ref={trapRef} tabIndex={-1} className="pmerge-modal" role="dialog" aria-modal aria-labelledby="pmerge-title">
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
              {aiAvailable && (
                <button
                  type="button"
                  className="pmerge-ai-normalize"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    void handleNormalize()
                  }}
                  disabled={normalizePayee.isPending}
                  title="Normalize with AI — clean up the bank name"
                >
                  <Sparkles size={12} />
                  {normalizePayee.isPending ? 'Thinking…' : 'Normalize'}
                </button>
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

          <label className="pmerge-checkbox-row">
            <input type="checkbox" checked={usePattern} onChange={togglePattern} />
            <span className="pmerge-checkbox-row__text">
              <Regex size={13} aria-hidden />
              Set a match pattern (regex)
            </span>
          </label>
          <p className="pmerge-hint">
            Incoming transactions whose payee matches this pattern map to the surviving payee —
            useful when banks append random codes. Case-insensitive.
          </p>

          {usePattern && (
            <div className="pmerge-pattern">
              <div className="pmerge-pattern__input-row">
                <input
                  className="pmerge-pattern__input"
                  type="text"
                  value={pattern}
                  onChange={(e) => setPattern(e.target.value)}
                  placeholder={'e.g. ^ACH DEPOSIT PAYROLL'}
                  spellCheck={false}
                  aria-label="Match pattern"
                  aria-invalid={patternInvalid}
                />
                {suggestion && pattern !== suggestion && (
                  <button
                    type="button"
                    className="pmerge-pattern__suggest"
                    onClick={() => setPattern(suggestion)}
                    title="Use the pattern suggested from the selected payee names"
                  >
                    Suggest
                  </button>
                )}
              </div>
              {patternInvalid ? (
                <p className="pmerge-pattern__error">Invalid regular expression</p>
              ) : !suggestion && !trimmedPattern ? (
                <p className="pmerge-hint">
                  These names share no obvious structure — write a pattern by hand if you still
                  want one.
                </p>
              ) : (
                trimmedPattern && (
                  <ul className="pmerge-pattern__tests">
                    {patternResults.map(({ name, matches }) => (
                      <li
                        key={name}
                        className={`pmerge-pattern__test ${matches ? 'pmerge-pattern__test--match' : 'pmerge-pattern__test--miss'}`}
                      >
                        {matches ? <Check size={12} aria-hidden /> : <X size={12} aria-hidden />}
                        <span className="pmerge-pattern__test-name">{name}</span>
                        {!matches && <span className="pmerge-pattern__test-label">no match</span>}
                      </li>
                    ))}
                  </ul>
                )
              )}
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
