import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * Every theme ships its own palette, and a palette that looks right can still
 * be unreadable — the 2026-08 audit found 41% of text pairings below WCAG AA
 * across the 40 variants, with one as low as 1.17:1. Hand-tuning fixed that
 * once; this test is what keeps it fixed when the 41st theme lands.
 *
 * Small print matters here: the UI renders most secondary text at 10-13px, so
 * the large-text exemption (>=18.66px bold / >=24px regular) never applies and
 * every pairing below owes the full 4.5:1.
 */

const THEMES_DIR = dirname(fileURLToPath(import.meta.url))

const AA_TEXT = 4.5
const AA_NON_TEXT = 3.0 // WCAG 1.4.11, for a border that is the only cue a control exists

/** Kept in step with the caps applied in component CSS. */
const BADGE_TINT = 12
const CHIP_TINT = 18
/** Sidebar.css: the account balance chip, resting / hovered / negative. */
const BALANCE_CHIP_TINT = 8
const BALANCE_CHIP_HOVER_TINT = 14
const NEGATIVE_CHIP_TINT = 24

type RGBA = [number, number, number, number]

// ---------------------------------------------------------------- parsing

/**
 * Top-level rules only. Anything wrapped in an at-rule (the prefers-contrast
 * layer) is skipped: those overrides are conditional, so folding them into the
 * base token maps would test a state the default render never reaches.
 */
function topLevelRules(src: string): Array<[string, string]> {
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

/** token maps per theme, plus the `:root` defaults every theme falls back to */
function loadThemes(): { themes: Map<string, Map<string, string>>; root: Map<string, string> } {
  const themes = new Map<string, Map<string, string>>()
  const root = new Map<string, string>()

  for (const file of readdirSync(THEMES_DIR).filter((f) => f.endsWith('.css'))) {
    const src = readFileSync(join(THEMES_DIR, file), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
    for (const [selector, body] of topLevelRules(src)) {
      const targets: Map<string, string>[] = []
      for (const part of selector.split(',')) {
        const named = part.match(/\[data-theme="([^"]+)"\]\s*$/)
        if (named) {
          if (!themes.has(named[1])) themes.set(named[1], new Map())
          targets.push(themes.get(named[1])!)
        } else if (/^\s*:root(:not\([^)]*\))?\s*$/.test(part)) {
          targets.push(root)
        }
      }
      if (!targets.length) continue
      for (const decl of body.split(';')) {
        const at = decl.indexOf(':')
        if (at < 0) continue
        const name = decl.slice(0, at).trim()
        if (!name.startsWith('--')) continue
        const value = decl.slice(at + 1).trim()
        for (const t of targets) t.set(name, value)
      }
    }
  }
  return { themes, root }
}

const { themes, root } = loadThemes()

/** split on top-level commas only, so nested var()/color-mix() survive */
function splitTop(input: string): string[] {
  const out: string[] = []
  let depth = 0
  let cur = ''
  for (const ch of input) {
    if (ch === '(') depth++
    else if (ch === ')') depth--
    if (ch === ',' && depth === 0) {
      out.push(cur.trim())
      cur = ''
    } else cur += ch
  }
  if (cur.trim()) out.push(cur.trim())
  return out
}

function parseHex(hex: string): RGBA | null {
  let h = hex.slice(1)
  if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join('')
  if (h.length !== 6 && h.length !== 8) return null
  const n = (i: number) => parseInt(h.slice(i, i + 2), 16)
  return [n(0), n(2), n(4), h.length === 8 ? n(6) / 255 : 1]
}

function resolve(theme: string, value: string | undefined, depth = 0): RGBA | null {
  if (!value || depth > 12) return null
  const v = value.trim()
  if (v === 'transparent') return [0, 0, 0, 0]
  if (v === 'white') return [255, 255, 255, 1]
  if (v === 'black') return [0, 0, 0, 1]
  if (v.startsWith('#')) return parseHex(v)

  const varMatch = v.match(/^var\(\s*(--[\w-]+)\s*(?:,([\s\S]+))?\)$/)
  if (varMatch) {
    const direct = resolve(theme, lookup(theme, varMatch[1]), depth + 1)
    if (direct) return direct
    return varMatch[2] ? resolve(theme, varMatch[2], depth + 1) : null
  }

  const rgbMatch = v.match(/^rgba?\(([^)]*)\)$/)
  if (rgbMatch) {
    const parts = rgbMatch[1].split(/[,\s/]+/).filter(Boolean).map(Number)
    if (parts.length < 3 || parts.some(Number.isNaN)) return null
    return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1]
  }

  const mixMatch = v.match(/^color-mix\(\s*in\s+srgb\s*,([\s\S]+)\)$/)
  if (mixMatch) {
    const args = splitTop(mixMatch[1])
    if (args.length !== 2) return null
    const parsed = args.map((arg) => {
      const pct = arg.match(/\s(\d+(?:\.\d+)?)%$/)
      return {
        color: pct ? arg.slice(0, pct.index).trim() : arg,
        weight: pct ? Number(pct[1]) : null,
      }
    })
    let [w1, w2] = [parsed[0].weight, parsed[1].weight]
    if (w1 === null && w2 === null) [w1, w2] = [50, 50]
    else if (w1 === null) w1 = 100 - (w2 as number)
    else if (w2 === null) w2 = 100 - w1
    const total = (w1 as number) + (w2 as number)
    if (total <= 0) return null
    const a = resolve(theme, parsed[0].color, depth + 1)
    const b = resolve(theme, parsed[1].color, depth + 1)
    if (!a || !b) return null
    const [f1, f2] = [(w1 as number) / total, (w2 as number) / total]
    const alpha = a[3] * f1 + b[3] * f2
    if (alpha === 0) return [0, 0, 0, 0]
    const chan = (i: number) => (a[i] * a[3] * f1 + b[i] * b[3] * f2) / alpha
    return [chan(0), chan(1), chan(2), alpha]
  }
  return null
}

function lookup(theme: string, token: string): string | undefined {
  return themes.get(theme)?.get(token) ?? root.get(token)
}

function token(theme: string, name: string): RGBA | null {
  return resolve(theme, lookup(theme, `--${name}`))
}

// ---------------------------------------------------------------- contrast

function channel(c: number): number {
  const s = c / 255
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

function luminance([r, g, b]: RGBA): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

/** composite a possibly-translucent colour over an opaque backdrop */
function over(fg: RGBA, bg: RGBA): RGBA {
  return [
    fg[0] * fg[3] + bg[0] * (1 - fg[3]),
    fg[1] * fg[3] + bg[1] * (1 - fg[3]),
    fg[2] * fg[3] + bg[2] * (1 - fg[3]),
    1,
  ]
}

function contrast(fg: RGBA, bg: RGBA): number {
  const base = bg[3] < 1 ? over(bg, [255, 255, 255, 1]) : bg
  const top = luminance(over(fg, base))
  const bottom = luminance(base)
  const [hi, lo] = top > bottom ? [top, bottom] : [bottom, top]
  return (hi + 0.05) / (lo + 0.05)
}

/** `color-mix(in srgb, colour pct%, transparent)` painted onto a surface */
function tint(colour: RGBA, surface: RGBA, pct: number): RGBA {
  const a = colour[3] * (pct / 100)
  return [
    colour[0] * a + surface[0] * (1 - a),
    colour[1] * a + surface[1] * (1 - a),
    colour[2] * a + surface[2] * (1 - a),
    1,
  ]
}

// ---------------------------------------------------------------- the contract

const SURFACES = [
  'bg-primary',
  'bg-secondary',
  'bg-tertiary',
  'bg-elevated',
  'bg-hover',
  'card-bg',
  'input-bg',
  'header-bg',
]
/** surfaces a tinted badge or chip realistically sits on */
const TINT_BASES = ['bg-primary', 'bg-secondary', 'bg-tertiary']
const SEMANTIC = ['color-negative', 'color-positive', 'color-warning', 'color-info', 'color-accent']
const TAGS = ['red', 'orange', 'yellow', 'green', 'teal', 'blue', 'purple', 'pink']

interface Check {
  label: string
  ratio: number
  min: number
}

function checksFor(theme: string): Check[] {
  const out: Check[] = []
  const add = (label: string, fg: RGBA | null, bg: RGBA | null, min: number) => {
    if (fg && bg) out.push({ label, ratio: contrast(fg, bg), min })
  }

  // body and semantic text, on every surface it can land on.
  // --color-accent-hover is here because it is used as a text colour too,
  // not only as a fill (TransactionRow, CategoryInspector).
  for (const fg of ['text-primary', 'text-secondary', 'text-muted', ...SEMANTIC, 'color-accent-hover']) {
    for (const surface of SURFACES) {
      add(`${fg} on ${surface}`, token(theme, fg), token(theme, surface), AA_TEXT)
    }
  }

  // a badge tinted from its own colour — the background moves toward the text
  for (const fg of [...SEMANTIC, 'text-muted']) {
    const colour = token(theme, fg)
    for (const base of TINT_BASES) {
      const surface = token(theme, base)
      if (colour && surface) {
        add(
          `${fg} on its ${BADGE_TINT}% tint over ${base}`,
          colour,
          tint(colour, surface, BADGE_TINT),
          AA_TEXT
        )
      }
    }
  }

  // tag chips carry the hue in the wash and the label in the body colour
  for (const tag of TAGS) {
    const colour = token(theme, `tag-${tag}`)
    for (const base of TINT_BASES) {
      const surface = token(theme, base)
      if (colour && surface) {
        add(
          `tag-${tag} chip label over ${base}`,
          token(theme, 'text-primary'),
          tint(colour, surface, CHIP_TINT),
          AA_TEXT
        )
      }
    }
  }

  // text printed on top of a solid themed fill (buttons, the selection bar)
  for (const fill of [
    'color-accent',
    'color-accent-hover',
    'color-warning',
    'color-negative',
    'color-positive',
  ]) {
    add(`text-inverse on ${fill}`, token(theme, 'text-inverse'), token(theme, fill), AA_TEXT)
    add(`bg-primary on ${fill}`, token(theme, 'bg-primary'), token(theme, fill), AA_TEXT)
  }

  // Derived badge tokens, resolved from the CSS rather than reconstructed, so
  // the real color-mix() percentage in the theme file is what gets measured.
  // They are translucent, so they have to be painted onto a surface first.
  for (const [fg, bg] of [
    ['color-info-text', 'color-info-bg'],
    ['color-negative', 'color-negative-bg'],
  ]) {
    const text = token(theme, fg)
    const wash = token(theme, bg)
    for (const base of TINT_BASES) {
      const surface = token(theme, base)
      if (text && wash && surface) {
        add(`${fg} on ${bg} over ${base}`, text, over(wash, surface), AA_TEXT)
      }
    }
  }

  // the sidebar keeps its own dark background in every theme
  for (const fg of ['sidebar-text-primary', 'sidebar-text-secondary', 'sidebar-text-muted']) {
    add(`${fg} on sidebar-bg`, token(theme, fg), token(theme, 'sidebar-bg'), AA_TEXT)
  }

  // The account balance chip. Its wash is derived from the sidebar's own text
  // colour, which means it moves the background TOWARD the text — so the
  // label loses a little contrast for the sake of the chip being visible at
  // all, and that trade has to be measured rather than assumed. The negative
  // variant is a tint of --color-negative, which is not otherwise checked
  // against sidebar-bg anywhere.
  const sidebarBg = token(theme, 'sidebar-bg')
  const neutralChip =
    sidebarBg && token(theme, 'sidebar-text-primary')
      ? tint(token(theme, 'sidebar-text-primary')!, sidebarBg, BALANCE_CHIP_TINT)
      : null
  const label = token(theme, 'sidebar-text-primary')
  add('balance chip label, resting', label, neutralChip, AA_TEXT)
  add(
    'balance chip label, row hovered',
    label,
    sidebarBg && label ? tint(label, sidebarBg, BALANCE_CHIP_HOVER_TINT) : null,
    AA_TEXT
  )
  add(
    'balance chip label on the negative chip',
    label,
    sidebarBg && token(theme, 'color-negative')
      ? tint(token(theme, 'color-negative')!, sidebarBg, NEGATIVE_CHIP_TINT)
      : null,
    AA_TEXT
  )

  add(
    'input-border on input-bg',
    token(theme, 'input-border'),
    token(theme, 'input-bg'),
    AA_NON_TEXT
  )
  return out
}

const THEME_NAMES = [...themes.keys()].sort()

// ---------------------------------------------------------------- surfaces

/**
 * The surface ladder. Sections were invisible because cards painted
 * themselves the canvas colour and, in the themes that did step up, the step
 * was 3-4 pt of lightness with a border the same colour as the next surface.
 * These floors are the picked contract (surface picker, 2026-08-25: an 8-pt
 * lightness step, hairlines mixed 14% toward the text colour) measured on the
 * generated ladders and floored — WCAG ratios compress near white, so a light
 * theme scores lower for the same visual step and gets its own floors.
 *
 * Every number below fails against the ladders that shipped before this
 * contract: Desert Dark's step measured 1.13, and the light themes' hairline
 * (--border-subtle on white) measured 1.06.
 */
const SURFACE_STEP_MIN = { dark: 1.18, light: 1.08 } // canvas -> raised
// raised -> overlay. Overlays carry --shadow-lg and a scrim, so this floor only
// guards direction and non-zero; the text colours cap how far the overlay can
// go (Phosphor's text-muted tops out at +9 pt) and win over a bigger step.
const OVERLAY_STEP_MIN = { dark: 1.03 }
const EDGE_MIN = { dark: 1.34, light: 1.23 } // hairline on the raised surface it outlines
const EDGE_STRONG_MIN = { dark: 1.6, light: 1.45 } // strong rule on the canvas

function surfaceChecksFor(theme: string): Check[] {
  const out: Check[] = []
  const canvas = token(theme, 'surface-canvas')
  const raised = token(theme, 'surface-raised')
  const overlay = token(theme, 'surface-overlay')
  const edge = token(theme, 'edge')
  const strong = token(theme, 'edge-strong')
  if (!canvas || !raised || !overlay || !edge || !strong) return out
  const mode = luminance(canvas) < 0.5 ? 'dark' : 'light'
  out.push({ label: `${mode}: canvas -> raised step`, ratio: contrast(canvas, raised), min: SURFACE_STEP_MIN[mode] })
  if (mode === 'dark') {
    out.push({ label: 'dark: raised -> overlay step', ratio: contrast(raised, overlay), min: OVERLAY_STEP_MIN.dark })
  }
  out.push({ label: `${mode}: hairline (--edge) on raised`, ratio: contrast(edge, raised), min: EDGE_MIN[mode] })
  out.push({ label: `${mode}: strong edge on canvas`, ratio: contrast(strong, canvas), min: EDGE_STRONG_MIN[mode] })
  return out
}

describe('theme palettes', () => {
  it('finds every shipped theme', () => {
    expect(THEME_NAMES.length).toBeGreaterThanOrEqual(40)
  })

  it('declares no malformed colour values', () => {
    const bad: string[] = []
    for (const file of readdirSync(THEMES_DIR).filter((f) => f.endsWith('.css'))) {
      const src = readFileSync(join(THEMES_DIR, file), 'utf8')
      for (const [, name, hex] of src.matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]+)/g)) {
        if (![3, 4, 6, 8].includes(hex.length - 1)) bad.push(`${file} ${name}: ${hex}`)
      }
    }
    expect(bad).toEqual([])
  })

  it.each(THEME_NAMES)('%s steps its surfaces apart', (theme) => {
    const canvas = token(theme, 'surface-canvas')
    const raised = token(theme, 'surface-raised')
    const overlay = token(theme, 'surface-overlay')
    expect(canvas && raised && overlay).toBeTruthy()
    // Direction is universal: a raised surface is LIGHTER than the canvas in
    // every theme, including phosphor-light (dark-on-dark by design). This is
    // the check the four inverted ladders (Catppuccin, Gruvbox, Nord, Nord
    // Aurora) failed before they were re-tuned.
    expect(luminance(raised!)).toBeGreaterThan(luminance(canvas!))
    expect(luminance(overlay!)).toBeGreaterThanOrEqual(luminance(raised!))
    const checks = surfaceChecksFor(theme)
    expect(checks.length).toBeGreaterThanOrEqual(3)
    const failures = checks
      .filter((c) => c.ratio < c.min)
      .map((c) => `${c.label} — ${c.ratio.toFixed(2)}:1 (needs ${c.min}:1)`)
    expect(failures).toEqual([])
  })

  it.each(THEME_NAMES)('%s meets WCAG AA', (theme) => {
    const checks = checksFor(theme)
    // guards the resolver: a silent parse failure would drop pairs and pass
    expect(checks.length).toBeGreaterThan(80)
    const failures = checks
      .filter((c) => c.ratio < c.min)
      .map((c) => `${c.label} — ${c.ratio.toFixed(2)}:1 (needs ${c.min}:1)`)
    expect(failures).toEqual([])
  })
})
