import { useState } from 'react'
import { glossaryEntry } from '../../content/glossary'

/**
 * Terms offered alongside a roadmap node.
 *
 * Deliberately a quiet row under the body rather than links woven through the
 * prose: definitions should be reachable the moment someone wants one, and
 * invisible to everyone else. Opening one expands a card in place — no modal,
 * no navigation, nothing that costs the reader their position on the page.
 */
export function GlossaryChips({ terms }: { terms: string[] }) {
  const [open, setOpen] = useState<string | null>(null)
  const entry = open ? glossaryEntry(open) : undefined

  if (!terms.length) return null

  return (
    <div className="guide-terms">
      <div className="guide-terms__row">
        <span className="guide-terms__label">Terms</span>
        {terms.map((id) => {
          const e = glossaryEntry(id)
          if (!e) return null
          const isOpen = open === id
          return (
            <button
              key={id}
              type="button"
              className={`guide-term ${isOpen ? 'guide-term--open' : ''}`}
              aria-expanded={isOpen}
              onClick={() => setOpen(isOpen ? null : id)}
            >
              {e.term}
            </button>
          )
        })}
      </div>
      {entry && (
        <div className="guide-terms__card" role="note">
          <p className="guide-terms__short">{entry.short}</p>
          <p className="guide-terms__body">{entry.body}</p>
          {entry.inIgab && (
            <p className="guide-terms__in-app">
              <span className="guide-terms__in-app-label">In IGAB</span>
              {entry.inIgab}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
