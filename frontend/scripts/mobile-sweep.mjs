#!/usr/bin/env node
/**
 * Phone-width screenshot sweep with geometry checks.
 *
 * Loads every route (and, per route, the sheets that open from it) in a
 * headless Chrome at phone and landscape sizes, saves a PNG of each, and
 * reports the things jsdom cannot see: horizontal overflow, boxes that
 * escape the viewport or their parent, interactive controls under 44px,
 * sibling boxes that overlap, and text clipped without an ellipsis. The
 * PNGs are for a person to look at; the report is what fails the run.
 *
 * Chrome cannot emulate the installed-PWA safe-area insets, so the top and
 * bottom edges are still judged from device screenshots — the ruler in
 * Settings → Mobile is for that.
 *
 *   just mobile-sweep                      # against http://localhost:5173
 *   IGAB_URL=http://192.168.1.10:5173 IGAB_USER=… IGAB_PASS=… just mobile-sweep
 *   just mobile-sweep --routes /budget,/accounts --only-portrait
 *   just mobile-sweep --create-sample     # make the full demo budget if none
 *
 * Needs the dev stack running with a budget that has data (the sample budget
 * is enough) and the credentials in IGAB_USER / IGAB_PASS.
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import puppeteer from 'puppeteer-core'
import { BASE, CHROME, api, flag, login, opt, sampleBudget, seedPage } from './lib/igabSession.mjs'

const OUT = resolve(process.env.IGAB_SWEEP_OUT ?? '../mobile-sweep')

const VIEWPORTS = [
  { name: 'phone', width: 390, height: 844 },
  ...(flag('--only-portrait') ? [] : [{ name: 'landscape', width: 844, height: 390 }]),
]

const REPORT_TABS = [
  'overview',
  'net-worth',
  'account-composition',
  'liabilities',
  'savings',
  'savings-rate',
  'essentials',
  'emergency-fund',
  'income-expense',
  'income-sources',
  'cost-of-living',
  'wishlist',
  'burn-rate',
  'cash-flow',
  'projection',
  'budget-actual',
  'category-history',
  'variance',
  'volatility',
  'spending-trends',
  'spending-breakdown',
  'pareto',
  'treemap',
  'seasonality',
  'subscriptions',
  'plan-reality',
  'anomalies',
  'payees',
  'day-patterns',
  'timeline',
]

/** Sheets and modals opened from a route, by the selector that opens them. */
const TRIGGERS = {
  '/budget': [
    { name: 'quick-add', open: 'button[aria-label="Add transaction"]' },
    { name: 'more', open: '.bottom-nav button:last-child' },
    { name: 'assign', open: '.tba-hero__assign-main' },
    { name: 'filters', open: '.budget-filter-bar__views-trigger, .budget-filter-bar button' },
  ],
  '/accounts/:id': [
    { name: 'editor', open: '.transaction-row' },
    { name: 'row-menu', open: '.txn-more-btn' },
  ],
  '/transactions': [{ name: 'editor', open: '.transaction-row' }],
  '/reports': [{ name: 'report-picker', open: '.reports-nav__dropdown-trigger' }],
  '/scheduled': [{ name: 'editor', open: '.sched-btn--primary' }],
  '/accounts': [{ name: 'account-settings', open: '.accounts-overview__action-btn' }],
  '/liabilities/:id': [
    { name: 'balance', open: 'button[class*="balance"], button[class*="update"]' },
  ],
}

const TAP_MIN = 44

async function routesFor(token) {
  const budget = await sampleBudget(token, { create: flag('--create-sample') })
  const [accounts, liabilities, assets] = await Promise.all([
    api(`/${budget.id}/accounts`, token),
    api(`/${budget.id}/liabilities`, token).catch(() => []),
    api(`/${budget.id}/assets`, token).catch(() => []),
  ])
  const routes = [
    '/budget',
    '/accounts',
    '/transactions',
    '/scheduled',
    '/payees',
    '/guide',
    '/wishlist',
    '/liabilities',
    '/assets',
    '/settings',
    '/system',
    '/activity',
    '/ai-activity',
    '/import',
    '/budgets',
    ...(accounts[0] ? [`/accounts/${accounts[0].id}`] : []),
    ...(liabilities[0] ? [`/liabilities/${liabilities[0].id}`] : []),
    ...(assets[0] ? [`/assets/${assets[0].id}`] : []),
    ...REPORT_TABS.map((t) => `/reports?tab=${t}`),
  ]
  const only = opt('--routes')
  return { budget, routes: only ? only.split(',') : routes }
}

/** Runs inside the page: the geometry report. */
function audit(tapMin) {
  const vw = document.documentElement.clientWidth
  const name = (el) => {
    const cls = (el.className && typeof el.className === 'string' ? el.className : '')
      .split(/\s+/)
      .filter(Boolean)[0]
    return cls ? `${el.tagName.toLowerCase()}.${cls}` : el.tagName.toLowerCase()
  }
  const visible = (el) => {
    const r = el.getBoundingClientRect()
    if (r.width === 0 || r.height === 0) return false
    const cs = getComputedStyle(el)
    return cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0'
  }
  const findings = []
  // What the checks ignore, and why:
  //   svg descendants   chart marks overlap by design (paths, groups, text)
  //   .sr-only          clipped on purpose — that is what the class is for
  //   .skip-link        off-screen until focused
  //   inside a horizontal scroller   a wide table inside overflow-x:auto is
  //                     the fix for width, not the bug; its cells exceed the
  //                     viewport by design and the container is what scrolls
  const inSvg = (el) => !!el.closest('svg')
  const inScroller = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX
      if (ox === 'auto' || ox === 'scroll') return true
    }
    return false
  }
  const ignored = (el) =>
    inSvg(el) || el.matches('.sr-only, .skip-link') || !!el.closest('.sr-only')
  const scroller = document.scrollingElement
  if (scroller && scroller.scrollWidth > scroller.clientWidth + 1) {
    findings.push({ kind: 'page-overflow-x', by: scroller.scrollWidth - scroller.clientWidth })
  }
  // A vertical scroller that is also scrollable sideways. This is the check
  // that would have caught the budget page sliding 46px left and back: a
  // .sr-only span inside the status strip took the sticky filter bar as its
  // containing block, escaped the strip's clip, and widened the page. The
  // symptom is invisible to the checks below, which skip anything under an
  // overflow-x scroller as "wide by design".
  //
  // overflow-x hidden still counts: it clips the paint but the box is still
  // over-wide, so this reports the cause after a fix has hidden the effect.
  // Only a container that opted INTO sideways scrolling (auto/scroll) is
  // exempt, and only when it is not also the page's vertical scroller.
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el)
    const scrollsY = cs.overflowY === 'auto' || cs.overflowY === 'scroll'
    const wantsX = cs.overflowX === 'auto' || cs.overflowX === 'scroll'
    if (!scrollsY || wantsX) continue
    if (el.scrollWidth <= el.clientWidth + 1) continue
    findings.push({
      kind: 'scroller-overflow-x',
      el: name(el),
      by: el.scrollWidth - el.clientWidth,
    })
  }
  const all = Array.from(document.querySelectorAll('body *')).filter(
    (el) => visible(el) && !ignored(el)
  )
  for (const el of all) {
    const r = el.getBoundingClientRect()
    if (r.right > vw + 1 && getComputedStyle(el).position !== 'fixed' && !inScroller(el)) {
      findings.push({ kind: 'exceeds-viewport', el: name(el), right: Math.round(r.right), vw })
    }
    const p = el.parentElement
    if (p && p !== document.body) {
      const pr = p.getBoundingClientRect()
      const pcs = getComputedStyle(p)
      const clips = pcs.overflowX !== 'visible'
      if (!clips && r.right > pr.right + 1 && pr.width > 0) {
        findings.push({
          kind: 'exceeds-parent',
          el: name(el),
          parent: name(p),
          by: Math.round(r.right - pr.right),
        })
      }
    }
  }
  const controls = Array.from(
    document.querySelectorAll(
      'button, a[href], input:not([type=hidden]), select, [role=button], [role=tab], [role=option]'
    )
  ).filter((el) => visible(el) && !ignored(el))
  for (const el of controls) {
    const r = el.getBoundingClientRect()
    if (r.height < tapMin - 1 && !el.closest('.sidebar')) {
      findings.push({
        kind: 'small-target',
        el: name(el),
        h: Math.round(r.height),
        w: Math.round(r.width),
      })
    }
  }
  // Sibling overlap: two visible, non-positioned siblings whose boxes intersect
  // by more than a pixel. The crushed-flex-row signature.
  const parents = new Set(all.map((el) => el.parentElement).filter((p) => p && !inSvg(p)))
  for (const p of parents) {
    // Inline children of a wrapping paragraph have bounding boxes that span
    // lines and "overlap" each other by construction; only block-level and
    // flex/grid items can genuinely collide.
    const kids = Array.from(p.children).filter((k) => {
      const cs = getComputedStyle(k)
      return (
        visible(k) &&
        !ignored(k) &&
        ['static', 'relative'].includes(cs.position) &&
        cs.display !== 'inline'
      )
    })
    for (let i = 0; i < kids.length; i++) {
      const a = kids[i].getBoundingClientRect()
      for (let j = i + 1; j < kids.length; j++) {
        const b = kids[j].getBoundingClientRect()
        const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left)
        const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
        if (ox > 2 && oy > 2) {
          findings.push({
            kind: 'sibling-overlap',
            a: name(kids[i]),
            b: name(kids[j]),
            parent: name(p),
            ox: Math.round(ox),
            oy: Math.round(oy),
          })
        }
      }
    }
  }
  // Clipped text without an ellipsis — and text crushed to almost nothing
  // WITH one: an ellipsis on a 20px-wide cell is a crushed flex row hiding
  // behind a tidy "…" (the Activity page's actor column read "A…").
  for (const el of all) {
    if (el.children.length || inScroller(el)) continue
    if (el.scrollWidth <= el.clientWidth + 1) continue
    const cs = getComputedStyle(el)
    if (cs.overflowX === 'visible') continue
    const text = (el.textContent || '').trim().slice(0, 40)
    if (cs.textOverflow !== 'ellipsis') findings.push({ kind: 'clipped-text', el: name(el), text })
    else if (el.clientWidth < 48 && el.scrollWidth > el.clientWidth * 2)
      findings.push({
        kind: 'crushed-text',
        el: name(el),
        w: el.clientWidth,
        need: el.scrollWidth,
        text,
      })
  }
  return findings
}

async function main() {
  const tokens = await login()
  const { budget, routes } = await routesFor(tokens.access_token)
  await mkdir(OUT, { recursive: true })
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true })
  const report = []
  try {
    for (const vp of VIEWPORTS) {
      const page = await browser.newPage()
      await page.setViewport({
        width: vp.width,
        height: vp.height,
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true,
      })
      await seedPage(page, tokens, budget.id)
      for (const route of routes) {
        const slug = `${vp.name}${route.replace(/[/?=:]+/g, '_')}`
        try {
          await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle0', timeout: 30000 })
          await new Promise((r) => setTimeout(r, 400))
          await page.screenshot({ path: resolve(OUT, `${slug}.png`) })
          const findings = await page.evaluate(audit, TAP_MIN)
          report.push({ view: slug, route, viewport: vp.name, findings })
          const key = route.replace(/\/[0-9a-f-]{20,}/, '/:id').replace(/\?.*/, '')
          for (const trig of TRIGGERS[key] ?? []) {
            const el = await page.$(trig.open)
            if (!el) continue
            await el.click().catch(() => {})
            await new Promise((r) => setTimeout(r, 500))
            const s2 = `${slug}__${trig.name}`
            await page.screenshot({ path: resolve(OUT, `${s2}.png`) })
            const f2 = await page.evaluate(audit, TAP_MIN)
            report.push({ view: s2, route, viewport: vp.name, sheet: trig.name, findings: f2 })
            await page.keyboard.press('Escape')
            await new Promise((r) => setTimeout(r, 300))
          }
        } catch (err) {
          report.push({ view: slug, route, viewport: vp.name, error: String(err.message || err) })
        }
      }
      await page.close()
    }
  } finally {
    await browser.close()
  }
  await writeFile(resolve(OUT, 'report.json'), JSON.stringify(report, null, 2))
  // Geometry — overflow, overlap, clipping — fails the run. Sub-44px targets
  // are counted as debt and fail only with --strict: there are hundreds
  // across the desktop-density surfaces, and a run that is always red says
  // nothing about the crushed-row class this exists to catch.
  const strict = flag('--strict')
  const isDebt = (f) => f.kind === 'small-target'
  let bad = 0
  let debt = 0
  for (const r of report) {
    if (r.error) {
      console.log(`ERR  ${r.view}: ${r.error}`)
      bad++
      continue
    }
    const failing = r.findings.filter((f) => strict || !isDebt(f))
    debt += r.findings.filter(isDebt).length
    const counts = {}
    for (const f of r.findings) counts[f.kind] = (counts[f.kind] || 0) + 1
    const summary = Object.entries(counts)
      .map(([k, n]) => `${k}=${n}`)
      .join(' ')
    console.log(`${failing.length ? 'FAIL' : 'ok  '} ${r.view} ${summary}`)
    for (const f of failing.slice(0, 12)) console.log(`       ${JSON.stringify(f)}`)
    if (failing.length) bad++
  }
  console.log(
    `\n${report.length - bad}/${report.length} views clean; ${debt} sub-44px targets${strict ? '' : ' (debt, --strict to fail on them)'} → ${OUT}/report.json`
  )
  process.exit(bad ? 1 : 0)
}

main().catch((err) => {
  console.error(err)
  process.exit(2)
})
