import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments, type ContextRule } from '../test-utils/cssRules'
import { escapeRegex } from '../utils/payeeRegex'

/**
 * The 16px input floor: it lives once, and it wins.
 *
 * iOS zooms the viewport into any focused control under 16px, and the app's
 * viewport tokens deliberately freeze while zoomed — one undersized input
 * made a whole page look broken. base.css floors every text control.
 *
 * The first floor was the right value in a rule that could not win: bare
 * `input, select, textarea` (specificity 0,0,1) under
 * `(hover: none) and (max-width: 768px)`. Every `.txn-editor__input {
 * font-size: var(--font-size-sm) }` outranked it, so the register, the
 * budget and nearly every form zoomed on focus with the floor sitting right
 * there — and a phone held sideways, or an iPad, was outside the width cap
 * anyway. The old test only checked that the rule existed.
 *
 * jsdom computes no cascade, so this is a proof over the stylesheets rather
 * than a measurement. An author declaration marked !important beats every
 * normal one whatever its specificity; among important ones only another
 * important declaration, or a cascade layer, could take precedence. So: the
 * floor is important and unconditional on width, no other stylesheet
 * declares an important font-size, and nothing uses @layer. Inline styles
 * from React cannot be important. Together those mean no rule anywhere can
 * set a text control under 16px on a touch device.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

function files(dir: string, ext: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return files(full, ext)
    return full.endsWith(ext) ? [full] : []
  })
}

const read = (f: string) => readFileSync(f, 'utf8')
const sheets = files(SRC, '.css').map((f) => ({
  file: relative(SRC, f),
  rules: rulesWithContext(stripComments(read(f))),
  src: stripComments(read(f)),
}))
const base = sheets.find((s) => s.file === 'themes/base.css')!

const FLOOR_VALUE = /font-size:\s*max\(16px,\s*var\(--control-font-size,\s*1em\)\)\s*!important/
const selectors = (r: ContextRule) => r.selector.split(/,(?![^(]*\))/).map((s) => s.trim())

describe('the iOS focus-zoom floor', () => {
  const floors = base.rules.filter((r) => FLOOR_VALUE.test(r.body))

  it('is declared once, in base.css, as an important declaration', () => {
    expect(floors).toHaveLength(1)
  })

  it('covers every text control: input, select and textarea', () => {
    const sel = selectors(floors[0])
    expect(sel.some((s) => /^input(?::not\(|$)/.test(s))).toBe(true)
    expect(sel).toContain('select')
    expect(sel).toContain('textarea')
  })

  it('leaves out only input types iOS never zooms to', () => {
    const input = selectors(floors[0]).find((s) => s.startsWith('input'))!
    const excluded = [...input.matchAll(/\[type="(\w+)"\]/g)].map((m) => m[1]).sort()
    expect(excluded).toEqual(['checkbox', 'color', 'file', 'radio', 'range'])
  })

  it('applies on every touch device, with no width or height condition', () => {
    // (max-width: 768px) left landscape phones and iPads zooming.
    const { atRules } = floors[0]
    expect(atRules).toHaveLength(1)
    expect(atRules[0]).toMatch(/^@media\s*\(hover:\s*none\)$/)
  })

  it('cannot be outranked: no other stylesheet declares font-size !important', () => {
    const rivals = sheets.flatMap(({ file, rules }) =>
      rules
        .filter((r) => r !== floors[0])
        .filter((r) => /font(?:-size)?\s*:[^;]*!important/.test(r.body))
        .map((r) => `${file}: ${r.selector}`)
    )
    expect(rivals, 'an important font-size can beat the floor on a control').toEqual([])
  })

  it('cannot be outranked by a cascade layer', () => {
    // Important declarations in a layer beat unlayered important ones.
    const layered = sheets.filter((s) => /@layer\b/.test(s.src)).map((s) => s.file)
    expect(layered).toEqual([])
  })

  it('cannot be outranked from script', () => {
    const scripted = [...files(SRC, '.ts'), ...files(SRC, '.tsx')]
      .filter((f) => !/\.test\.tsx?$/.test(f))
      .filter((f) => /setProperty\(\s*['"]font-size['"][^)]*important/.test(read(f)))
      .map((f) => relative(SRC, f))
    expect(scripted).toEqual([])
  })

  it('is written nowhere else', () => {
    // Six components once carried their own phone-only 16px; each was a copy
    // free to drift.
    const copies = sheets
      .filter((s) => s.file !== 'themes/base.css')
      .flatMap(({ file, rules }) =>
        rules
          .filter((r) => r.atRules.some((a) => /hover:\s*none|max-width/.test(a)))
          .filter((r) => /(?:^|[;\s])font-size:\s*(?:16px|max\(16px)/.test(r.body))
          .map((r) => `${file}: ${r.selector.trim()}`)
      )
    expect(copies, 'base.css already floors this control at 16px on touch devices').toEqual([])
  })
})

// ─── Controls larger than the floor keep their size ─────────────────────────

/** The attribute text of each JSX opening tag named `tag`, braces balanced. */
function openingTags(src: string, tag: string): string[] {
  const out: string[] = []
  const re = new RegExp(`<${tag}\\b`, 'g')
  for (let m = re.exec(src); m; m = re.exec(src)) {
    let depth = 0
    let i = m.index + m[0].length
    for (; i < src.length; i++) {
      const c = src[i]
      if (c === '{') depth++
      else if (c === '}') depth--
      else if (c === '>' && depth === 0) break
    }
    out.push(src.slice(m.index, i))
  }
  return out
}

const classNameOf = (attrs: string) => attrs.match(/\bclassName=(\{[\s\S]*\}|"[^"]*")/)?.[1] ?? null

const classTokens = (expr: string) => expr.match(/[a-z][a-z0-9]*(?:(?:-|__|--)[a-z0-9]+)+/g) ?? []

/**
 * Every class a text control can carry: written on an input, select or
 * textarea, or passed to a component that forwards its className onto one
 * (AmountInput, InlineInput, DatePicker).
 */
function controlClasses(): Set<string> {
  const tsx = files(SRC, '.tsx').filter((f) => !f.endsWith('.test.tsx'))
  const classes = new Set<string>()
  const forwarders = new Set<string>()
  for (const f of tsx) {
    const src = read(f)
    for (const tag of ['input', 'select', 'textarea']) {
      for (const attrs of openingTags(src, tag)) {
        const cn = classNameOf(attrs)
        if (!cn) continue
        classTokens(cn).forEach((c) => classes.add(c))
        if (/\bclassName\b/.test(cn.slice(1))) {
          for (const m of src.matchAll(/export (?:const|function) ([A-Z]\w*)/g))
            forwarders.add(m[1])
        }
      }
    }
  }
  for (const f of tsx) {
    const src = read(f)
    for (const name of forwarders) {
      for (const attrs of openingTags(src, name)) {
        const cn = classNameOf(attrs)
        if (cn) classTokens(cn).forEach((c) => classes.add(c))
      }
    }
  }
  return classes
}

/** base.css's font-size tokens, as rem multiples. */
const TOKENS: Record<string, number> = Object.fromEntries(
  [...base.src.matchAll(/(--font-size-[\w-]+):\s*([\d.]+)rem/g)].map((m) => [m[1], Number(m[2])])
)

/**
 * Whether a declared font-size is larger than what the floor would draw it
 * at. The floor is max(16px, 1em), and 1em is the surrounding text: the root
 * size, which follows the reader's browser font setting. So a length above
 * 16px is clamped, and so is anything sized above 1rem — the reconcile
 * figure's 1.125rem is under 16px at the default setting and above it at a
 * larger one, where it would sink back to the size of the text around it.
 */
function largerThanFloor(value: string): boolean {
  const v = value.trim()
  const lit = v.match(/^([\d.]+)(px|rem)$/)
  if (lit) return lit[2] === 'px' ? Number(lit[1]) > 16 : Number(lit[1]) > 1
  const token = v.match(/^var\((--font-size-[\w-]+)\)$/)
  return token ? (TOKENS[token[1]] ?? 0) > 1 : false
}

describe('a control larger than the floor', () => {
  const classes = controlClasses()
  const targetsControl = (selector: string) => {
    const last = selector.split(/\s*[\s>+~]\s*(?![^(]*\))/).pop() ?? ''
    if (/^(input|select|textarea)\b/.test(last)) return true
    return (last.match(/\.[\w-]+/g) ?? []).some((c) => classes.has(c.slice(1)))
  }
  const controlRules = sheets
    .filter((s) => s.file !== 'themes/base.css')
    .flatMap(({ file, rules }) =>
      rules.flatMap((r) =>
        selectors(r)
          .filter(targetsControl)
          .map((selector) => ({ file, selector, body: r.body }))
      )
    )

  it('finds the controls (a green run must mean something)', () => {
    expect(classes.size).toBeGreaterThan(80)
    // The register's editor field, the budget's assign input via AmountInput,
    // and the inline register cell via InlineInput.
    for (const c of ['txn-editor__input', 'category-row__input', 'inline-input']) {
      expect(classes, c).toContain(c)
    }
    const sized = controlRules.filter((r) => /(?:^|[;\s])font-size\s*:/.test(r.body))
    expect(sized.length).toBeGreaterThan(60)
  })

  it('states its size in --control-font-size, which the floor reads', () => {
    // The floor overrides font-size outright: a 34px amount written as
    // font-size would be drawn at 16px on every touch device.
    const shrunk = controlRules.flatMap(({ file, selector, body }) => {
      const m = body.match(/(?:^|[;\s])font-size\s*:\s*([^;]+)/)
      return m && largerThanFloor(m[1]) ? [`${file}: ${selector} (${m[1].trim()})`] : []
    })
    expect(shrunk, 'use --control-font-size for a control larger than its text').toEqual([])
  })

  it('reads a length or token the way the floor does', () => {
    expect(largerThanFloor('34px')).toBe(true)
    expect(largerThanFloor('16px')).toBe(false)
    expect(largerThanFloor('var(--font-size-lg)')).toBe(true)
    expect(largerThanFloor('var(--font-size-sm)')).toBe(false)
    expect(largerThanFloor('1rem')).toBe(false)
  })

  it('keeps the two it was written for', () => {
    const declares = (file: string, selector: string, value: string) =>
      controlRules.some(
        (r) =>
          r.file === file &&
          r.selector === selector &&
          new RegExp(`--control-font-size:\\s*${escapeRegex(value)}`).test(r.body)
      )
    expect(
      declares(
        'components/transactions/QuickAddSheet/QuickAddSheet.css',
        '.quick-add__amount input',
        '34px'
      )
    ).toBe(true)
    expect(
      declares(
        'components/accounts/ReconcileModal.css',
        '.reconcile-modal__input',
        'var(--font-size-lg)'
      )
    ).toBe(true)
  })

  it('declares --control-font-size only on a control, where it is read', () => {
    // It does not inherit, so on a wrapper it silently does nothing.
    const stray = sheets
      .filter((s) => s.file !== 'themes/base.css')
      .flatMap(({ file, rules }) =>
        rules
          .filter((r) => /--control-font-size\s*:/.test(r.body))
          .flatMap((r) => selectors(r).filter((s) => !targetsControl(s)))
          .map((s) => `${file}: ${s}`)
      )
    expect(stray).toEqual([])
  })
})
