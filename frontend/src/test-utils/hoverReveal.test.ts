import { describe, expect, it } from 'vitest'
import { hoverRevealReport, subject } from './hoverReveal'

/**
 * The guard's own tests. A guard that passes over the bug it was written for
 * is worse than none — it would have said the Activity page was fine.
 */

const HIDDEN = `.x__btn { display: flex; opacity: 0; transition: opacity 0.1s; }`
const HOVER = `.x:hover .x__btn, .x__btn:focus-visible { opacity: 1; }`

describe('hoverRevealReport', () => {
  it('reports a control hidden at top level and revealed only by :hover', () => {
    // The Activity page's revert line, as shipped.
    const r = hoverRevealReport(`${HIDDEN}\n${HOVER}`)
    expect(r.unrestored).toEqual(['.x__btn'])
  })

  it('is satisfied by a (hover: none) restore', () => {
    const r = hoverRevealReport(
      `${HIDDEN}\n${HOVER}\n@media (hover: none) { .x__btn { opacity: 1; } }`
    )
    expect(r.hoverRevealed).toEqual(['.x__btn'])
    expect(r.unrestored).toEqual([])
  })

  it('is satisfied by a phone-width restore', () => {
    const r = hoverRevealReport(
      `${HIDDEN}\n${HOVER}\n@media (max-width: 768px) { .x__btn { opacity: 1; } }`
    )
    expect(r.unrestored).toEqual([])
  })

  it('is satisfied by a component-driven state, which a phone can enter', () => {
    // Long-press enters selection mode; every row's checkbox then shows.
    const r = hoverRevealReport(`${HIDDEN}\n${HOVER}\n.x--selected .x__btn { opacity: 1; }`)
    expect(r.unrestored).toEqual([])
  })

  it('is satisfied when the hiding itself only happens with a pointer', () => {
    const r = hoverRevealReport(
      `@media (hover: hover) { .x__btn { opacity: 0; } .x:hover .x__btn { opacity: 1; } }`
    )
    expect(r.unrestored).toEqual([])
  })

  it('ignores a control removed deliberately in a touch context', () => {
    // The register's add button: display:none on phones because the FAB is
    // the add path; its :hover rule is a colour, not a reveal.
    const r = hoverRevealReport(
      `.add { display: flex; background: red; }\n.add:hover { background: blue; }\n@media (max-width: 768px) { .add { display: none; } }`
    )
    expect(r.hoverRevealed).toEqual([])
  })

  it('does not mistake a dimmed control for a hidden one', () => {
    const r = hoverRevealReport(`.dim { opacity: 0.6; }\n.dim:hover { opacity: 1; }`)
    expect(r.hoverRevealed).toEqual([])
  })

  it('does not count :focus-visible as a touch path', () => {
    const r = hoverRevealReport(
      `${HIDDEN}\n.x__btn:focus-visible { opacity: 1; }\n.x:hover .x__btn { opacity: 1; }`
    )
    expect(r.unrestored).toEqual(['.x__btn'])
  })
})

describe('subject', () => {
  it('is the last compound with pseudo-classes stripped', () => {
    expect(subject('.row:hover .row__btn')).toBe('.row__btn')
    expect(subject('.row__btn:focus-visible')).toBe('.row__btn')
    expect(subject('.a > .b + .c::before')).toBe('.c')
  })
})
