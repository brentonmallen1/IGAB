import { Check, X } from 'lucide-react'
import {
  claimedNames,
  compilePattern,
  matchSpan,
  testPattern,
  type ClaimablePayee,
} from '../../../utils/payeeRegex'
import type { PatternCandidate } from './patternCandidates'
import './PatternSuggest.css'

/**
 * Choosing and previewing a payee match pattern.
 *
 * Two pieces, used wherever a pattern is authored — the merge modal and the
 * Payees page editor — so a pattern reads the same in both:
 *
 * - `PatternCandidates`: the suggestions as chips. Each says, live, how many
 *   of the names it claims and how many *other* payees it would also claim,
 *   because on import the longest matching pattern wins and a general one
 *   that swallows a neighbour is a real cost.
 * - `PatternMatchPreview`: the names, with the part the pattern captured
 *   highlighted, and the ones it misses marked.
 */

const SOURCE_LABEL: Record<PatternCandidate['source'], string> = {
  ai: 'AI',
  structural: 'From the names',
}

function summarise(pattern: string, names: string[], others: ClaimablePayee[]): string {
  if (compilePattern(pattern) === null) return 'not a valid regular expression'
  const hits = names.filter((n) => testPattern(pattern, n) === true).length
  const claimed = claimedNames(pattern, others).length
  const othersText =
    claimed === 0 ? 'no other payees' : `also ${claimed} other payee${claimed === 1 ? '' : 's'}`
  return `matches ${hits} of ${names.length} · ${othersText}`
}

export function PatternCandidates({
  candidates,
  value,
  names,
  others,
  onPick,
}: {
  candidates: PatternCandidate[]
  /** The pattern in the input — the chip that equals it reads as pressed. */
  value: string
  /** The names the pattern is meant to claim. */
  names: string[]
  /** Payees it must not claim by accident. */
  others: ClaimablePayee[]
  onPick: (pattern: string) => void
}) {
  if (candidates.length === 0) return null
  return (
    <ul className="pattern-candidates" aria-label="Suggested patterns">
      {candidates.map((c) => {
        const claims = claimedNames(c.pattern, others).length > 0
        return (
          <li key={c.pattern}>
            <button
              type="button"
              className="pattern-chip"
              aria-pressed={c.pattern === value}
              onClick={() => onPick(c.pattern)}
              title="Use this pattern"
            >
              <code className="pattern-chip__pattern">{c.pattern}</code>
              <span className="pattern-chip__meta">
                <span className="pattern-chip__source">{SOURCE_LABEL[c.source]}</span>
                <span className={claims ? 'pattern-chip__claims' : undefined}>
                  {summarise(c.pattern, names, others)}
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export function PatternMatchPreview({ pattern, names }: { pattern: string; names: string[] }) {
  if (!pattern || compilePattern(pattern) === null) return null
  return (
    <ul className="pattern-preview scroll-list" aria-label="Which names this pattern matches">
      {names.map((name) => {
        const span = matchSpan(pattern, name)
        return (
          <li
            key={name}
            className={`pattern-preview__row ${span ? 'pattern-preview__row--match' : 'pattern-preview__row--miss'}`}
          >
            {span ? <Check size={12} aria-hidden /> : <X size={12} aria-hidden />}
            <span className="pattern-preview__name">
              {span ? (
                <>
                  {name.slice(0, span.start)}
                  <mark>{name.slice(span.start, span.end)}</mark>
                  {name.slice(span.end)}
                </>
              ) : (
                name
              )}
            </span>
            {!span && <span className="pattern-preview__label">no match</span>}
          </li>
        )
      })}
    </ul>
  )
}
