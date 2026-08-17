import { useState, useRef, useEffect, useMemo } from 'react'
import { AlertTriangle, Check, GitMerge, Regex, Sparkles, X } from 'lucide-react'
import type { PayeeWithCount } from '../../../api/payees'
import { useAIStatus, useNormalizePayee, useSuggestRegex } from '../../../api/ai'
import { useAppStore } from '../../../stores/appStore'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import { Combobox } from '../../common/Combobox/Combobox'
import { suggestPayeeRegex, testPattern, unionPatterns } from '../../../utils/payeeRegex'
import './PayeeMergeModal.css'

export interface MergeConfig {
  targetId: string
  addToMappingSamples: boolean
  customName?: string
  matchPattern?: string
}

interface Props {
  payees: PayeeWithCount[]
  /** Full payee list — enables merging the group into a payee outside it. */
  allPayees: PayeeWithCount[]
  onConfirm: (config: MergeConfig) => void
  onCancel: () => void
  isPending: boolean
}

type TargetMode = 'member' | 'external' | 'custom'
type PatternAction = 'keep' | 'extend' | 'replace'

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

function splitSamples(samples: string | null | undefined): string[] {
  return samples?.split(',').map((s) => s.trim()).filter(Boolean) ?? []
}

function nameList(names: string[], max = 3): string {
  const shown = names.slice(0, max).map((n) => `"${n}"`)
  const rest = names.length - shown.length
  return rest > 0 ? `${shown.join(', ')} and ${rest} more` : shown.join(', ')
}

export function PayeeMergeModal({ payees, allPayees, onConfirm, onCancel, isPending }: Props) {
  const sorted = [...payees].sort((a, b) => b.transaction_count - a.transaction_count)
  const [mode, setMode] = useState<TargetMode>('member')
  const [targetId, setTargetId] = useState(sorted[0]?.id ?? '')
  const [externalId, setExternalId] = useState<string | null>(null)
  const [customName, setCustomName] = useState('')
  const [addToMappingSamples, setAddToMappingSamples] = useState(true)
  const [usePattern, setUsePattern] = useState(false)
  const [patternAction, setPatternAction] = useState<PatternAction>('keep')
  const [pattern, setPattern] = useState('')
  const trapRef = useFocusTrap<HTMLDivElement>(onCancel)
  const customInputRef = useRef<HTMLInputElement>(null)
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const aiAvailable = useAIStatus().data?.available === true
  const normalizePayee = useNormalizePayee(budgetId ?? '')
  const suggestRegex = useSuggestRegex(budgetId ?? '')

  // AI cleanup of the surviving name: feeds the messiest raw name through
  // normalize-payee and drops the result into the custom-name input.
  async function handleNormalize() {
    const source = customName.trim() || sorted[0]?.name
    if (!source) return
    const normalized = await normalizePayee.mutateAsync(source)
    setMode('custom')
    setCustomName(normalized)
  }

  useEffect(() => {
    if (mode === 'custom') customInputRef.current?.focus()
  }, [mode])

  // Payees outside the merge group that can serve as an external target
  // (transfer payees are managed automatically and can't absorb merges).
  const externalOptions = useMemo(() => {
    const groupIds = new Set(payees.map((p) => p.id))
    return allPayees
      .filter((p) => !groupIds.has(p.id) && !p.transfer_account_id)
      .map((p) => ({ id: p.id, label: p.name }))
  }, [allPayees, payees])

  // The payee that survives the merge. In custom mode the selected member is
  // renamed; in external mode an existing payee outside the group absorbs all
  // group members.
  const effectiveTarget =
    mode === 'external'
      ? allPayees.find((p) => p.id === externalId)
      : payees.find((p) => p.id === targetId)

  // Every raw name this merge represents: payee names plus their recorded
  // bank-name samples (including the external target's, when one is chosen).
  // Feeds the suggestion, the live match preview, and conflict checks.
  const rawNames = useMemo(() => {
    const pool =
      mode === 'external' && effectiveTarget ? [...payees, effectiveTarget] : payees
    const names = pool.flatMap((p) => [p.name, ...splitSamples(p.mapping_samples)])
    return [...new Set(names.filter(Boolean))]
  }, [payees, mode, effectiveTarget])

  const suggestion = useMemo(() => suggestPayeeRegex(rawNames), [rawNames])

  // Pattern reconciliation: when the surviving payee already has a match
  // pattern, the choice is keep it, extend it (union with a new one), or
  // replace it outright.
  const existingPattern = (effectiveTarget?.match_pattern ?? '').trim()
  const existingPatternValid = existingPattern ? testPattern(existingPattern, '') !== null : false
  const hasExistingPattern = existingPattern.length > 0

  const effectiveTargetId = effectiveTarget?.id
  useEffect(() => {
    setPatternAction('keep')
  }, [effectiveTargetId])

  function togglePattern() {
    setUsePattern((on) => {
      if (!on && !pattern && suggestion) setPattern(suggestion)
      return !on
    })
  }

  function choosePatternAction(action: PatternAction) {
    setPatternAction(action)
    if (action !== 'keep' && !pattern && suggestion) setPattern(suggestion)
  }

  const patternEditing = hasExistingPattern ? patternAction !== 'keep' : usePattern
  const trimmedPattern = pattern.trim()
  const extendUnion =
    hasExistingPattern && patternAction === 'extend' && trimmedPattern
      ? unionPatterns(existingPattern, trimmedPattern)
      : null

  // The pattern the surviving payee ends up with (undefined = leave as-is).
  const finalPattern = !patternEditing
    ? undefined
    : patternAction === 'extend' && hasExistingPattern
      ? (extendUnion ?? undefined)
      : trimmedPattern || undefined

  // Preview tests the pattern as it will actually be stored — for Extend
  // that's the union, for Keep the existing one.
  const previewPattern = patternEditing
    ? (finalPattern ?? trimmedPattern)
    : hasExistingPattern
      ? existingPattern
      : ''
  const patternResults = previewPattern
    ? rawNames.map((name) => ({ name, matches: testPattern(previewPattern, name) }))
    : []
  const patternInvalid =
    patternEditing &&
    trimmedPattern.length > 0 &&
    (testPattern(trimmedPattern, '') === null ||
      (patternAction === 'extend' && hasExistingPattern && extendUnion === null))

  const sources = mode === 'external' ? payees : payees.filter((p) => p.id !== targetId)
  const reassignedCount = sources.reduce((sum, p) => sum + p.transaction_count, 0)
  const survivingName =
    mode === 'custom' ? (customName.trim() || '…') : (effectiveTarget?.name ?? '…')

  // Names the surviving payee absorbs into its fuzzy match list — in custom
  // mode the renamed payee's old name becomes a sample too.
  const sampleSources = mode === 'custom' ? payees : sources
  const previewMappings = addToMappingSamples
    ? deduplicateSamples([
        mode === 'custom' ? null : effectiveTarget?.mapping_samples,
        ...sampleSources.map((p) => p.name),
        ...sampleSources.map((p) => p.mapping_samples),
      ])
    : mode === 'custom' ? null : (effectiveTarget?.mapping_samples ?? '')

  // Non-blocking conflict checks against payees uninvolved in this merge:
  // does our final pattern claim their names, or do their patterns claim the
  // names we're absorbing?
  const conflictWarnings = useMemo(() => {
    const groupIds = new Set(payees.map((p) => p.id))
    const others = allPayees.filter(
      (p) => !groupIds.has(p.id) && p.id !== effectiveTargetId && !p.transfer_account_id
    )
    const warnings: string[] = []

    if (finalPattern && testPattern(finalPattern, '') !== null) {
      const claimed = others.filter(
        (p) =>
          testPattern(finalPattern, p.name) === true ||
          splitSamples(p.mapping_samples).some((s) => testPattern(finalPattern, s) === true)
      )
      if (claimed.length > 0) {
        warnings.push(
          `This pattern also matches ${nameList(claimed.map((p) => p.name))} — imports for those names could map here instead.`
        )
      }
    }

    const rivals = others.filter((p) => {
      const pp = (p.match_pattern ?? '').trim()
      if (!pp || testPattern(pp, '') === null) return false
      return rawNames.some((n) => testPattern(pp, n) === true)
    })
    if (rivals.length > 0) {
      warnings.push(
        `${nameList(rivals.map((p) => p.name))} ${rivals.length === 1 ? 'has a pattern' : 'have patterns'} that also match the absorbed names — on import, the longest matching pattern wins.`
      )
    }
    return warnings
  }, [allPayees, payees, effectiveTargetId, finalPattern, rawNames])

  const patternOk = !patternEditing || (trimmedPattern.length > 0 && !patternInvalid)
  const targetOk =
    mode === 'custom'
      ? customName.trim().length > 0 && !!targetId
      : mode === 'external'
        ? !!effectiveTarget
        : !!targetId
  const canConfirm = !isPending && patternOk && targetOk

  function handleConfirm() {
    if (!effectiveTarget) return
    const config: MergeConfig = {
      targetId: effectiveTarget.id,
      addToMappingSamples,
      matchPattern: finalPattern,
    }
    if (mode === 'custom') config.customName = customName.trim()
    onConfirm(config)
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
              <label key={p.id} className={`pmerge-option ${mode === 'member' && targetId === p.id ? 'pmerge-option--selected' : ''}`}>
                <input
                  type="radio"
                  name="target"
                  value={p.id}
                  checked={mode === 'member' && targetId === p.id}
                  onChange={() => { setTargetId(p.id); setMode('member') }}
                />
                <span className="pmerge-option__name">{p.name}</span>
                <span className="pmerge-option__count">{p.transaction_count} txn</span>
              </label>
            ))}
            <label className={`pmerge-option pmerge-option--custom ${mode === 'external' ? 'pmerge-option--selected' : ''}`}>
              <input
                type="radio"
                name="target"
                value="__external__"
                checked={mode === 'external'}
                onChange={() => setMode('external')}
              />
              {mode === 'external' ? (
                <Combobox
                  className="pmerge-external-combobox"
                  value={externalId}
                  options={externalOptions}
                  onChange={setExternalId}
                  placeholder="Search payees…"
                  autoFocus
                  aria-label="Merge into an existing payee"
                />
              ) : (
                <span className="pmerge-option__name pmerge-option__name--placeholder">Merge into an existing payee…</span>
              )}
            </label>
            <label className={`pmerge-option pmerge-option--custom ${mode === 'custom' ? 'pmerge-option--selected' : ''}`}>
              <input
                type="radio"
                name="target"
                value="__custom__"
                checked={mode === 'custom'}
                onChange={() => setMode('custom')}
              />
              {mode === 'custom' ? (
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

          {hasExistingPattern ? (
            <>
              <span className="pmerge-checkbox-row pmerge-checkbox-row--static">
                <span className="pmerge-checkbox-row__text">
                  <Regex size={13} aria-hidden />
                  Match pattern (regex)
                </span>
              </span>
              <p className="pmerge-hint">
                <strong>{effectiveTarget?.name}</strong> already has a pattern:{' '}
                <code className="pmerge-existing-pattern">{existingPattern}</code>
              </p>
              <div className="pmerge-pattern-actions" role="radiogroup" aria-label="Pattern reconciliation">
                <label className="pmerge-pattern-action">
                  <input
                    type="radio"
                    name="pattern-action"
                    checked={patternAction === 'keep'}
                    onChange={() => choosePatternAction('keep')}
                  />
                  <span>Keep</span>
                </label>
                <label className={`pmerge-pattern-action ${!existingPatternValid ? 'pmerge-pattern-action--disabled' : ''}`}>
                  <input
                    type="radio"
                    name="pattern-action"
                    checked={patternAction === 'extend'}
                    onChange={() => choosePatternAction('extend')}
                    disabled={!existingPatternValid}
                  />
                  <span>Extend</span>
                </label>
                <label className="pmerge-pattern-action">
                  <input
                    type="radio"
                    name="pattern-action"
                    checked={patternAction === 'replace'}
                    onChange={() => choosePatternAction('replace')}
                  />
                  <span>Replace</span>
                </label>
              </div>
              {!existingPatternValid && (
                <p className="pmerge-hint">
                  The stored pattern isn't a valid regex, so it can't be extended — keep it or
                  replace it.
                </p>
              )}
              {patternAction === 'extend' && (
                <p className="pmerge-hint">
                  The new pattern is combined with the existing one — names matching either
                  will map to the surviving payee.
                </p>
              )}
            </>
          ) : (
            <>
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
            </>
          )}

          {(patternEditing || (hasExistingPattern && existingPatternValid)) && (
            <div className="pmerge-pattern">
              {patternEditing && (
                <div className="pmerge-pattern__input-row">
                  <input
                    className="pmerge-pattern__input"
                    type="text"
                    value={pattern}
                    onChange={(e) => setPattern(e.target.value)}
                    placeholder={'e.g. ^ACH DEPOSIT PAYROLL'}
                    spellCheck={false}
                    aria-label={patternAction === 'extend' && hasExistingPattern ? 'Pattern to add' : 'Match pattern'}
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
                  {aiAvailable && (
                    <button
                      type="button"
                      className="pmerge-pattern__suggest pmerge-pattern__suggest--ai"
                      onClick={() => {
                        void suggestRegex
                          .mutateAsync(rawNames)
                          .then((p) => { if (p) setPattern(p) })
                      }}
                      disabled={suggestRegex.isPending}
                      title="Ask the AI for a pattern generalizing these names"
                    >
                      <Sparkles size={12} aria-hidden />
                      {suggestRegex.isPending ? 'Thinking…' : 'AI'}
                    </button>
                  )}
                </div>
              )}
              {patternInvalid ? (
                <p className="pmerge-pattern__error">Invalid regular expression</p>
              ) : patternEditing && !suggestion && !trimmedPattern ? (
                <p className="pmerge-hint">
                  These names share no obvious structure — write a pattern by hand if you still
                  want one.
                </p>
              ) : (
                previewPattern && (
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

          {conflictWarnings.length > 0 && (
            <ul className="pmerge-warnings">
              {conflictWarnings.map((w) => (
                <li key={w} className="pmerge-warning">
                  <AlertTriangle size={13} aria-hidden />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="pmerge-summary">
            <span className="pmerge-summary__surviving">
              Surviving: <strong>{survivingName}</strong>
            </span>
            {mode === 'custom' && effectiveTarget && customName.trim() && (
              <span className="pmerge-summary__detail">
                "{effectiveTarget.name}" will be renamed to "{customName.trim()}"
              </span>
            )}
            {mode === 'external' && effectiveTarget && (
              <span className="pmerge-summary__detail">
                All {payees.length} selected payees merge into this existing payee
              </span>
            )}
            <span className="pmerge-summary__detail">
              {sources.length} payee{sources.length !== 1 ? 's' : ''} absorbed · {reassignedCount} transaction{reassignedCount !== 1 ? 's' : ''} reassigned
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
