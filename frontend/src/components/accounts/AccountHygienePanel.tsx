import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronRight, X } from 'lucide-react'
import { useAccountHygiene, type HygieneFinding } from '../../api/accounts'
import './AccountHygienePanel.css'

/**
 * Things about this budget's accounts that are probably wrong.
 *
 * Deliberately quiet. It sits on the accounts page where you have already
 * chosen to look, never badges the nav, and says nothing at all when there is
 * nothing to say — a panel that always shows something is one people learn to
 * scroll past, and then the finding that matters goes past too.
 *
 * The budget it exists for: a real 47-account import where four assets had
 * been given debt types, understating net worth by ~$2.8M and spawning four
 * phantom payoff records, while 1,117 transfer legs arrived unpaired. Every
 * invariant held. The budget was still wrong, and nothing said so.
 */

const STORAGE_KEY = 'igab.hygiene.dismissed'

/** Dismissals are per-viewer and per-finding-kind, not per-budget-state: a
 *  finding you have decided to live with should stay gone, but a *new* kind
 *  of problem should still speak up. Wrapped because storage throws outright
 *  in some contexts (private windows, blocked site data). */
function readDismissed(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as string[]) : []
  } catch {
    return []
  }
}

function persistDismissed(kinds: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(kinds))
  } catch {
    // A viewer who cannot persist still gets the dismissal for this session.
  }
}

export function AccountHygienePanel({ budgetId }: { budgetId: string | null }) {
  const { data } = useAccountHygiene(budgetId)
  const [dismissed, setDismissed] = useState<string[]>(readDismissed)
  const navigate = useNavigate()

  function dismiss(kind: string) {
    const next = [...dismissed, kind]
    setDismissed(next)
    persistDismissed(next)
  }

  const findings = (data?.findings ?? []).filter((f) => !dismissed.includes(f.kind))
  if (findings.length === 0) return null

  // Only this one leads somewhere other than the accounts list itself.
  function target(f: HygieneFinding): string | null {
    return f.kind === 'unpaired_transfer_legs' ? '/transactions?q=is:unpaired' : null
  }

  return (
    <section className="hygiene" aria-label="Account suggestions">
      {findings.map((f) => (
        <div key={f.kind} className="hygiene__item">
          <AlertTriangle className="hygiene__icon" size={15} aria-hidden />
          <div className="hygiene__body">
            <div className="hygiene__title">{f.title}</div>
            <p className="hygiene__detail">{f.detail}</p>
            <p className="hygiene__action">
              {f.action}
              {target(f) && (
                <button
                  type="button"
                  className="hygiene__link"
                  onClick={() => navigate(target(f) as string)}
                >
                  Show them <ChevronRight size={12} />
                </button>
              )}
            </p>
          </div>
          <button
            type="button"
            className="hygiene__dismiss"
            onClick={() => dismiss(f.kind)}
            aria-label={`Dismiss: ${f.title}`}
            title="Dismiss — this kind of suggestion won't come back"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </section>
  )
}
