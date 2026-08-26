// Re-tunes every theme's surface ladder to the picked contract, then nudges
// any text or semantic colour the tighter ladder let sit within a hair of
// WCAG AA. It is what produced the 2026-08-25 ladders; run it again when a
// new theme lands and it will only touch that theme's surfaces.
//
//   node scripts/retune-surfaces.mjs src/themes            # dry run + table
//   node scripts/retune-surfaces.mjs src/themes --write    # rewrite in place
//
// The contract itself is enforced by src/themes/contrast.test.ts; this script
// is the tool that satisfies it, not the definition of it.
//
import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
const DIR = process.argv[2]
const WRITE = process.argv.includes('--write')
const STEP = 8, EDGE = 14
const OV = Number(process.env.OV ?? 16)   // overlay offset above canvas (dark)
const LT = Number(process.env.LT ?? 4)    // tint offset below canvas (light)
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
const hexToRgb = h => { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255] }
const rgbToHex = (r, g, b) => '#' + [r, g, b].map(v => clamp(Math.round(v), 0, 255).toString(16).padStart(2, '0')).join('')
function rgbToHsl([r, g, b]) { r /= 255; g /= 255; b /= 255; const max = Math.max(r, g, b), min = Math.min(r, g, b); let h = 0, s = 0; const l = (max + min) / 2; if (max !== min) { const d = max - min; s = l > .5 ? d / (2 - max - min) : d / (max + min); if (max === r) h = (g - b) / d + (g < b ? 6 : 0); else if (max === g) h = (b - r) / d + 2; else h = (r - g) / d + 4; h /= 6 } return [h * 360, s * 100, l * 100] }
function hslToRgb([h, s, l]) { h /= 360; s /= 100; l /= 100; if (s === 0) { const v = l * 255; return [v, v, v] } const q = l < .5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q; const f = t => { if (t < 0) t += 1; if (t > 1) t -= 1; if (t < 1 / 6) return p + (q - p) * 6 * t; if (t < .5) return q; if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6; return p }; return [f(h + 1 / 3) * 255, f(h) * 255, f(h - 1 / 3) * 255] }
const L = hex => rgbToHsl(hexToRgb(hex))[2]
const atL = (hex, l) => { const [h, s] = rgbToHsl(hexToRgb(hex)); return rgbToHex(...hslToRgb([h, s, clamp(l, 0, 100)])) }
const mix = (a, b, pct) => { const A = hexToRgb(a), B = hexToRgb(b), t = pct / 100; return rgbToHex(...A.map((v, i) => v + (B[i] - v) * t)) }
const lum = hex => { const [r, g, b] = hexToRgb(hex).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4 }); return .2126 * r + .7152 * g + .0722 * b }
const cr = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05) }

// Canonical palette surfaces, used instead of the derived value when within 2.5 pt L of it.
const SNAP = {
  'catppuccin-mocha': { secondary: '#313244', elevated: '#45475a' },
  'nord': { secondary: '#3b4252', elevated: '#4c566a' },
  'gruvbox-dark': { secondary: '#3c3836', elevated: '#504945' },
  'rose-pine': { elevated: '#403d52' },
  'rose-pine-moon': { elevated: '#44415a' },
}
const ALIASES = ['color-surface', 'color-border', 'color-text', 'color-text-muted', 'hover-bg', 'color-success', 'color-info-bg', 'color-info-border', 'color-info-text', 'card-bg', 'card-border']

const rows = []
for (const f of readdirSync(DIR).filter(f => f.endsWith('.css') && !['base.css', 'high-contrast.css'].includes(f))) {
  const path = `${DIR}/${f}`
  let src = readFileSync(path, 'utf8')
  const re = /\[data-theme="([^"]+)"\][^{]*\{/g
  let m, out = '', last = 0
  while ((m = re.exec(src))) {
    const name = m[1]
    const start = m.index + m[0].length
    const end = src.indexOf('\n}', start)
    let block = src.slice(start, end)
    const tok = k => (block.match(new RegExp(`^\\s*--${k}:\\s*([^;]+);`, 'm')) || [])[1]?.trim()
    const canvas0 = tok('bg-primary'), text = tok('text-primary')
    const dark = lum(canvas0) < 0.5
    let canvas = canvas0, raised, overlay, tint
    if (dark) {
      const l = L(canvas0)
      raised = atL(canvas0, l + STEP); overlay = atL(canvas0, l + OV); tint = mix(raised, overlay, 50)
    } else {
      const l0 = L(canvas0)
      const rl = Math.min(l0 + STEP, 100)
      raised = atL(canvas0, rl); canvas = atL(canvas0, rl - STEP); tint = atL(canvas0, rl - STEP - LT); overlay = raised
    }
    const input = dark ? canvas : tok('input-bg')
    const snap = SNAP[name] || {}
    const near = (a, b) => Math.abs(L(a) - L(b)) <= 3
    if (snap.secondary && near(snap.secondary, raised)) raised = snap.secondary
    const snappedOverlay = snap.elevated && near(snap.elevated, overlay) ? snap.elevated : null
    // --- AA guard, ported from contrast.test.ts: the largest overlay/tint
    // offsets this theme's text colours can carry. Raised stays at +8 (the
    // picked contract); anything it breaks is reported for a manual fix.
    const set = (k, v) => { block = block.replace(new RegExp(`^(\\s*--${k}:\\s*)[^;]+;`, 'm'), `$1${v};`) }
    const T = k => tok(k)
    const FG = ['text-primary', 'text-secondary', 'text-muted', 'color-negative', 'color-positive', 'color-warning', 'color-info', 'color-accent', 'color-accent-hover'].map(T)
    const SEM = ['color-negative', 'color-positive', 'color-warning', 'color-info', 'color-accent', 'text-muted'].map(T)
    const TAGS = ['red', 'orange', 'yellow', 'green', 'teal', 'blue', 'purple', 'pink'].map(t => T('tag-' + t))
    const AA = 4.53
    const textOK = S => FG.every(fg => cr(fg, S) >= AA)
    const tintOK = S => SEM.every(fg => cr(fg, mix(S, fg, 12)) >= AA) && TAGS.every(tg => cr(text, mix(S, tg, 18)) >= AA) && cr(T('color-negative'), mix(S, T('color-negative'), 10)) >= AA
    const problems = []
    if (dark) {
      const l = L(canvas0)
      let ov = OV
      while (ov > STEP + 1 && !textOK(atL(canvas0, l + ov))) ov -= 0.5
      overlay = snappedOverlay && textOK(snappedOverlay) ? snappedOverlay : atL(canvas0, l + ov)
      let tp = 50
      tint = mix(raised, overlay, tp)
      while (tp > 0 && !(textOK(tint) && tintOK(tint))) { tp -= 5; tint = mix(raised, overlay, tp) }
      if (ov !== OV || tp !== 50) problems.push(`overlay +${ov}, tint ${tp}%`)
    } else {
      const rl = L(raised)
      let lt = LT
      tint = atL(canvas0, rl - STEP - lt)
      while (lt > 0 && !(textOK(tint) && tintOK(tint))) { lt -= 0.5; tint = atL(canvas0, rl - STEP - lt) }
      if (lt !== LT) problems.push(`tint −${lt}`)
    }
    // --- Nudge. A text or semantic colour that the old, tighter ladder let
    // sit within a hair of 4.5:1 is moved 1 pt of lightness at a time (away
    // from the surfaces: lighter in dark themes, darker in light) until every
    // check it takes part in passes on every surface. Hue and saturation are
    // untouched. Chip washes are fixed by lifting text-primary instead of
    // muddying the tag hue.
    const surfaces = [canvas, raised, tint, overlay, tok('bg-hover')].filter(Boolean)
    const tintBases = [canvas, raised, tint]
    const dir = dark ? 1 : -1
    const cur = {}
    const fgNames = ['text-primary', 'text-secondary', 'text-muted', 'color-negative', 'color-positive', 'color-warning', 'color-info', 'color-accent', 'color-accent-hover']
    for (const k of fgNames) cur[k] = tok(k)
    const semNames = ['color-negative', 'color-positive', 'color-warning', 'color-info', 'color-accent', 'text-muted']
    const badgePct = k => (k === 'color-negative' ? [12, 10] : [12])
    const fgOK = k => surfaces.every(S => cr(cur[k], S) >= AA)
      && (!semNames.includes(k) || tintBases.every(S => badgePct(k).every(pc => cr(cur[k], mix(S, cur[k], pc)) >= AA)))
    const nudged = []
    for (const k of fgNames) {
      let steps = 0
      while (!fgOK(k) && steps < 8) { cur[k] = atL(cur[k], L(cur[k]) + dir); steps++ }
      if (steps) nudged.push(`${k} ${dir > 0 ? '+' : '-'}${steps}`)
      if (!fgOK(k)) problems.push(`${k} STILL FAILS`)
    }
    // tag chips: text-primary over an 18% wash of each tag on each surface
    {
      let steps = 0
      const chipsOK = () => TAGS.every(tg => tintBases.every(S => cr(cur['text-primary'], mix(S, tg, 18)) >= AA))
      while (!chipsOK() && steps < 8) { cur['text-primary'] = atL(cur['text-primary'], L(cur['text-primary']) + dir); steps++ }
      if (steps) nudged.push(`text-primary +${steps} (chips)`)
      if (!chipsOK()) problems.push('CHIPS STILL FAIL')
    }
    {
      let ib = tok('input-border'), steps = 0
      while (cr(ib, input) < 3.03 && steps < 12) { ib = atL(ib, L(ib) + dir); steps++ }
      if (steps) { set('input-border', ib); nudged.push(`input-border ${dir > 0 ? '+' : '-'}${steps}`) }
    }
    for (const k of fgNames) if (cur[k] !== tok(k)) set(k, cur[k])
    if (nudged.length) problems.push('nudged: ' + nudged.join(', '))
    if (problems.length) console.error(`${name.padEnd(22)} ${problems.join('; ')}`)
    const edge = mix(raised, text, EDGE)
    const strong = mix(canvas, text, EDGE * 1.8)
    set('bg-primary', canvas); set('bg-secondary', raised); set('bg-tertiary', tint); set('bg-elevated', overlay)
    set('border-subtle', edge); set('border-color', strong); set('input-bg', input)
    for (const a of ALIASES) block = block.replace(new RegExp(`^\\s*--${a}:[^\\n]*\\n`, 'm'), '')
    block = block.replace(/^\s*\/\* Aliases used by older components \*\/\n/m, '')
    block = block.replace(/\n{3,}/g, '\n\n').replace(/\n+$/, '')
    rows.push({ name, mode: dark ? 'dark' : 'light', canvas, raised, overlay, tint, edge, strong,
      step: cr(canvas, raised), ov: cr(raised, overlay), tintR: cr(canvas, tint), e: cr(edge, raised), eC: cr(edge, canvas), s: cr(strong, canvas), sR: cr(strong, raised),
      old: { step: cr(canvas0, tok('bg-secondary') ?? canvas0) } })
    out += src.slice(last, start) + block; last = end
  }
  out += src.slice(last)
  if (WRITE) writeFileSync(path, out)
}
const f2 = n => n.toFixed(2)
console.log('theme'.padEnd(22), 'mode ', 'canvas  raised  overlay tint    step  ovl   tint  edge/R edge/C strg/C strg/R')
for (const r of rows.sort((a, b) => a.mode.localeCompare(b.mode) || a.step - b.step))
  console.log(r.name.padEnd(22), r.mode.padEnd(5), r.canvas, r.raised, r.overlay, r.tint, f2(r.step), f2(r.ov), f2(r.tintR), f2(r.e), '  ' + f2(r.eC), '  ' + f2(r.s), '  ' + f2(r.sR))
const min = (mode, k) => Math.min(...rows.filter(r => r.mode === mode).map(r => r[k]))
console.log('\nMIN dark : step', f2(min('dark', 'step')), 'overlay', f2(min('dark', 'ov')), 'edge/raised', f2(min('dark', 'e')), 'strong/canvas', f2(min('dark', 's')))
console.log('MIN light: step', f2(min('light', 'step')), 'overlay', f2(min('light', 'ov')), 'edge/raised', f2(min('light', 'e')), 'strong/canvas', f2(min('light', 's')))
console.log(WRITE ? '\nWROTE theme files' : '\n(dry run — pass --write)')
