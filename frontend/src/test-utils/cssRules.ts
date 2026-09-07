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
