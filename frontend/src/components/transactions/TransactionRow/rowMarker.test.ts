/**
 * The row marker is one inset edge down the left of a register row, coloured
 * by whichever state claims it. It has to stay ONE declaration.
 *
 * It did not start that way: the AI-review marker and the pending marker each
 * reached for `box-shadow` in their own rule, and because
 * `.transaction-row.pending` outranks `.transaction-row--ai-review`, a row
 * that was both would have lost its review marker silently — a second rule
 * writing the same property is not a second marker, it is the first one
 * deleted. These read the real stylesheet and say so.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { stripComments, topLevelRules } from '../../../test-utils/cssRules'

const CSS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'TransactionRow.css'),
  'utf8'
)
const RULES = [...topLevelRules(stripComments(CSS))]

/** Rules whose selector targets a register row at all. */
const rowRules = RULES.filter(([sel]) => sel.includes('.transaction-row'))

describe('the row marker', () => {
  it('is set in exactly one place', () => {
    const setters = rowRules.filter(([, body]) => /(^|[;{\s])box-shadow\s*:/.test(body))
    expect(setters.map(([sel]) => sel.trim())).toEqual(['.transaction-row'])
  })

  it('takes its colour from a custom property, never a literal state colour', () => {
    const [, body] = rowRules.find(([sel]) => sel.trim() === '.transaction-row')!
    expect(body).toMatch(/box-shadow:\s*inset [^;]*var\(--row-marker\)/)
  })

  it('is transparent until a state claims it', () => {
    // Otherwise every ordinary row wears an edge and the marker says nothing.
    const [, body] = rowRules.find(([sel]) => sel.trim() === '.transaction-row')!
    expect(body).toMatch(/--row-marker:\s*transparent/)
  })

  it('is claimed by exactly one state — work waiting for a person', () => {
    // Pending claimed it too for one commit, to carry a hue its translucent
    // ground could not. Expanded, that put an edge beside every row in the
    // section and read as a box round the section; the ground carries pending
    // now. A second claimant is not a second signal — it is a race between two
    // rules over one property, and the reader cannot tell which won.
    const claimants = rowRules
      .filter(([, body]) => /--row-marker:\s*var\(/.test(body))
      .map(([sel]) => sel.trim())
    expect(claimants).toEqual(['.transaction-row.transaction-row--ai-review'])
  })
})
