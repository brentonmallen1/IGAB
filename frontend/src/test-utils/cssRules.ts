/**
 * A minimal CSS reader for tests that assert on the real stylesheets.
 *
 * jsdom has no layout, so no rendering test in this repo can see a panel run
 * off the screen or a column land under the wrong heading. What a test *can*
 * do is read the stylesheet and assert the contract that decides those
 * pixels. `contrast.test.ts` has done that for theme tokens since 2026-08;
 * this is the same parser, extracted when `overlayBounds.test.ts` became its
 * second reader rather than its second copy.
 */

/** Comments carry property names ("max-height arrives inline from…") that a
 *  naive scan reads as declarations. Strip them before anything else. */
export function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '')
}

/**
 * Top-level rules only, as `[selector, body]`. Anything wrapped in an at-rule
 * is skipped: those overrides are conditional, so folding them into a base
 * assertion would test a state the default render never reaches.
 */
export function topLevelRules(src: string): Array<[string, string]> {
  const rules: Array<[string, string]> = []
  let depth = 0
  let selectorStart = 0
  let bodyStart = 0
  for (let i = 0; i < src.length; i++) {
    if (src[i] === '{') {
      if (depth === 0) bodyStart = i + 1
      depth++
    } else if (src[i] === '}') {
      depth--
      if (depth === 0) {
        const selector = src.slice(selectorStart, bodyStart - 1)
        if (!selector.trimStart().startsWith('@')) rules.push([selector, src.slice(bodyStart, i)])
        selectorStart = i + 1
      }
    }
  }
  return rules
}

export interface ContextRule {
  selector: string
  body: string
  /** The at-rule preludes enclosing this rule, outermost first — e.g.
   *  `['@media (hover: none)']`. Empty for a top-level rule. */
  atRules: string[]
}

/**
 * Every rule, with the at-rules that wrap it. The complement of
 * `topLevelRules`: that one asks "what does the default render get", this
 * one lets a test ask "is there a `(hover: none)` variant of that rule" —
 * the question the hover-reveal guard needs. Recursive descent, kept simple
 * over fast; the stylesheets are small.
 */
export function rulesWithContext(
  src: string,
  atRules: string[] = [],
  out: ContextRule[] = []
): ContextRule[] {
  let i = 0
  while (i < src.length) {
    const open = src.indexOf('{', i)
    if (open < 0) break
    // A prelude never carries the declaration before it: inside an at-rule
    // body the text between the last `;`/`}` and this `{` is the selector.
    const prelude = src.slice(i, open).split(';').pop()!.trim()
    let depth = 1
    let j = open + 1
    while (j < src.length && depth > 0) {
      if (src[j] === '{') depth++
      else if (src[j] === '}') depth--
      j++
    }
    const body = src.slice(open + 1, j - 1)
    if (prelude.startsWith('@')) {
      rulesWithContext(body, [...atRules, prelude], out)
    } else if (prelude) {
      out.push({ selector: prelude, body, atRules })
    }
    i = j
  }
  return out
}
