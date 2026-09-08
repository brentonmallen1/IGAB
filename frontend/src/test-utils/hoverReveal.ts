import { rulesWithContext, stripComments, type ContextRule } from './cssRules'

/**
 * The hover-reveal heuristic, as a pure function over one stylesheet so the
 * guard test can be tested itself.
 *
 *   hidden control  a rule with no pseudo-class in its selector, outside any
 *                   touch context, whose body sets `opacity: 0`,
 *                   `visibility: hidden` or `display: none`; keyed by the
 *                   selector's last compound (the element the rule styles).
 *   hover reveal    any same-key rule whose selector contains `:hover` and
 *                   sets a visible value.
 *   touch restore   a same-key rule with no pseudo-class setting a visible
 *                   value — under `(hover: none)` / `(max-width: 768px)`, or
 *                   driven by a component state (`.row--selected .x`); or the
 *                   hidden rule itself sitting under `(hover: hover)`.
 *
 * Returns the keys that are hidden AND hover-revealed AND not restored.
 */

type HidingProp = 'opacity' | 'visibility' | 'display'

// `0` exactly: `opacity: 0.6` is dimmed, not hidden, and a dimmed control is reachable.
const HIDES: Record<HidingProp, RegExp> = {
  opacity: /(?:^|;)\s*opacity\s*:\s*0(?![.\d])/,
  visibility: /(?:^|;)\s*visibility\s*:\s*hidden/,
  display: /(?:^|;)\s*display\s*:\s*none/,
}

// Matched against the property that did the hiding — a body that says
// `display: flex; opacity: 0` is hidden, and its `display: flex` must not
// count as showing it.
const SHOWS: Record<HidingProp, RegExp> = {
  opacity: /(?:^|;)\s*opacity\s*:\s*(?:0?\.[1-9]\d*|1)(?![.\d])/,
  visibility: /(?:^|;)\s*visibility\s*:\s*visible/,
  display: /(?:^|;)\s*display\s*:\s*(?!none)[a-z-]+/,
}

const hidingProps = (body: string): HidingProp[] =>
  (Object.keys(HIDES) as HidingProp[]).filter((prop) => HIDES[prop].test(body))

const shows = (body: string, props: Set<HidingProp>): boolean =>
  [...props].some((prop) => SHOWS[prop].test(body))

/** The element a selector styles: its last compound, pseudo-classes removed. */
export function subject(selector: string): string {
  const last =
    selector
      .trim()
      .split(/\s+|>|\+|~/)
      .filter(Boolean)
      .pop() ?? ''
  return last.replace(/::?[a-z-]+(\([^)]*\))?/g, '')
}

const hasPseudoClass = (selector: string) => /:(?!:)[a-z-]+/.test(selector)
const isTouchContext = (atRules: string[]) =>
  atRules.some((a) => /\(hover:\s*none\)/.test(a) || /\(max-width:\s*768px\)/.test(a))
const isPointerContext = (atRules: string[]) => atRules.some((a) => /\(hover:\s*hover\)/.test(a))

export interface HoverRevealReport {
  /** Keys hidden and hover-revealed, restored or not — the pattern's reach. */
  hoverRevealed: string[]
  /** The subset with no touch path. */
  unrestored: string[]
}

interface Hidden {
  props: Set<HidingProp>
  /** Every hiding rule sits under (hover: hover), so touch never hides it. */
  underPointer: boolean
}

/** key → how it is hidden, for every control hidden outside a touch context. */
function collectHidden(rules: ContextRule[]): Map<string, Hidden> {
  const hidden = new Map<string, Hidden>()
  for (const r of rules) {
    const props = hidingProps(r.body)
    if (!props.length || isTouchContext(r.atRules)) continue
    for (const sel of r.selector.split(',')) {
      if (hasPseudoClass(sel)) continue
      const key = subject(sel)
      if (!key.startsWith('.')) continue
      const entry = hidden.get(key) ?? { props: new Set(), underPointer: true }
      for (const prop of props) entry.props.add(prop)
      entry.underPointer &&= isPointerContext(r.atRules)
      hidden.set(key, entry)
    }
  }
  return hidden
}

/** Whether a hidden control is revealed by :hover, and whether anything else shows it. */
function reveals(rules: ContextRule[], key: string, h: Hidden): { hover: boolean; other: boolean } {
  let hover = false
  let other = h.underPointer
  for (const r of rules) {
    if (!shows(r.body, h.props)) continue
    for (const sel of r.selector.split(',')) {
      if (subject(sel) !== key) continue
      if (sel.includes(':hover')) hover = true
      else if (!hasPseudoClass(sel)) other = true
    }
  }
  return { hover, other }
}

export function hoverRevealReport(css: string): HoverRevealReport {
  const rules = rulesWithContext(stripComments(css))
  const hoverRevealed: string[] = []
  const unrestored: string[] = []
  for (const [key, h] of collectHidden(rules)) {
    const { hover, other } = reveals(rules, key, h)
    if (!hover) continue
    hoverRevealed.push(key)
    if (!other) unrestored.push(key)
  }
  return { hoverRevealed, unrestored }
}
