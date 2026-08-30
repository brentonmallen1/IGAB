import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { GLOSSARY, glossaryEntry, searchGlossary } from '../../content/glossary'
import { useGuideStore } from '../../stores/guideStore'

/**
 * Every definition in one place, searchable.
 *
 * The same entries surface inline throughout the roadmap; this view is for
 * when someone arrives with the term already in mind rather than meeting it in
 * context.
 */
export function GlossaryPanel() {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<string | null>(null)

  // Arriving at one definition — from the command palette, or a chip
  // elsewhere in the app.
  //
  // Adjusted during render rather than in an effect: this is React's own
  // shape for "state that follows an incoming value", and an effect here
  // costs a cascading render (and trips react-hooks/set-state-in-effect).
  // `consumed` tracks the arrival we have already opened, so navigating to
  // the same term twice works even after the reader closed it.
  const arrivedAt = useGuideStore((s) => s.openGlossaryTerm)
  const setOpenGlossaryTerm = useGuideStore((s) => s.setOpenGlossaryTerm)
  const [consumed, setConsumed] = useState<string | null>(null)
  if (arrivedAt !== consumed) {
    setConsumed(arrivedAt)
    if (arrivedAt) setOpen(arrivedAt)
  }
  // Cleared once it has been read, so the reader's own folding takes over —
  // the same read-once-then-erase shape GuidePage uses for ?tab=.
  useEffect(() => {
    if (arrivedAt) setOpenGlossaryTerm(null)
  }, [arrivedAt, setOpenGlossaryTerm])

  const results = useMemo(() => searchGlossary(query), [query])

  return (
    <div className="guide-glossary">
      <header className="guide-roadmap__header">
        <div>
          <h2 className="guide-roadmap__title">Glossary</h2>
          <p className="guide-roadmap__lede">
            Plain-language definitions, and what each one means inside IGAB.
          </p>
        </div>
      </header>

      <div className="guide-glossary__search">
        <Search size={14} aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search terms…"
          aria-label="Search glossary"
        />
      </div>

      {results.length === 0 ? (
        <p className="guide-empty">
          No term matches “{query}”. {GLOSSARY.length} terms are defined — try a shorter word.
        </p>
      ) : (
        <ul className="guide-glossary__list surface">
          {results.map((entry) => {
            const isOpen = open === entry.id
            return (
              <li key={entry.id} className="guide-glossary__item">
                <button
                  type="button"
                  className="guide-glossary__term"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? null : entry.id)}
                >
                  <span className="guide-glossary__term-name">{entry.term}</span>
                  <span className="guide-glossary__term-short">{entry.short}</span>
                </button>
                {isOpen && (
                  <div className="guide-glossary__detail">
                    <p>{entry.body}</p>
                    {entry.inIgab && (
                      <p className="guide-terms__in-app">
                        <span className="guide-terms__in-app-label">In IGAB</span>
                        {entry.inIgab}
                      </p>
                    )}
                    {entry.related && entry.related.length > 0 && (
                      <div className="guide-terms__row">
                        <span className="guide-terms__label">See also</span>
                        {entry.related.map((id) => {
                          const rel = glossaryEntry(id)
                          if (!rel) return null
                          return (
                            <button
                              key={id}
                              type="button"
                              className="guide-term"
                              onClick={() => setOpen(id)}
                            >
                              {rel.term}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
