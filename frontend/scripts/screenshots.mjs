#!/usr/bin/env node
/**
 * Regenerate the README / screenshots-page tour.
 *
 * Drives a headless Chrome at desktop size against the running dev stack,
 * signed in to the *sample* budget (never a real one — this repository is
 * public), and writes one PNG per entry in SHOTS straight into screenshots/.
 * File names are the ones the README already links, so a rerun updates the
 * tour in place.
 *
 *   just screenshots                          # the five README shots
 *   just screenshots --all                    # every shot, including extras
 *   just screenshots --theme nord             # any palette id from PALETTES
 *   just screenshots --light                  # that palette's light variant
 *   just screenshots --only budget,loan
 *   just screenshots --month 2026-03-01       # override the budget month
 *   just screenshots --create-sample          # make the demo budget if none
 *
 * Needs the dev stack up and credentials in IGAB_USER / IGAB_PASS, or the
 * ADMIN_EMAIL / ADMIN_PASSWORD from .env (`just screenshots` sources it).
 */
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import puppeteer from 'puppeteer-core'
import { BASE, CHROME, api, flag, login, opt, sampleBudget, seedPage } from './lib/igabSession.mjs'

const OUT = resolve(process.env.IGAB_SHOTS_OUT ?? '../screenshots')
/** Matches the CSS size of the committed tour: 1440x960 at 2x. */
const VIEWPORT = {
  width: Number(opt('--width', 1440)),
  height: Number(opt('--height', 960)),
  deviceScaleFactor: 2,
}
/** Recharts animates in; this is how long to wait before the shutter. */
const SETTLE = Number(opt('--settle', 1400))
/**
 * Reports open on "This Month", and the demo data ends at the close of last
 * month — so the default range shows a dashboard of zeroes. Every report shot
 * clicks a wider window first.
 */
const RANGE = opt('--range', 'Last 12 Months')

/**
 * The tour. `route` may name an account or liability from the sample budget
 * by its label — ids differ per generated budget, so nothing here hard-codes
 * one. `extra: true` means it only runs under --all.
 */
const SHOTS = [
  { name: 'budget', route: () => '/budget' },
  { name: 'accounts', route: (r) => `/accounts/${r.account('Checking')}` },
  { name: 'accounts-overview', route: () => '/accounts' },
  { name: 'scheduled', route: () => '/scheduled' },
  // The payoff cards and the paydown curve are 1500px apart: this one shot
  // takes a taller frame rather than choosing between them.
  { name: 'loan', route: (r) => `/liabilities/${r.liability('Car Loan')}`, height: 1500 },
  { name: 'net-worth', route: () => '/reports?tab=net-worth', click: RANGE },
  { name: 'cash-flow', route: () => '/reports?tab=cash-flow', click: RANGE },
  { name: 'reports', route: () => '/reports?tab=pareto', click: RANGE },
  { name: 'reports2', route: () => '/reports?tab=overview', click: RANGE },
  { name: 'guide', route: () => '/guide' },
  { name: 'transactions', route: () => '/transactions', extra: true },
  {
    name: 'spending-breakdown',
    route: () => '/reports?tab=spending-breakdown',
    click: RANGE,
    extra: true,
  },
  { name: 'wishlist', route: () => '/wishlist', extra: true },
]

/** Palette id -> theme id, resolved the way the app resolves it. */
function themeFor(paletteId, light) {
  // Kept as a plain suffix rule rather than importing PALETTES: this script is
  // plain node with no TS pipeline. A bad id fails loudly on the next line.
  const known = {
    catppuccin: ['catppuccin-mocha', 'catppuccin-latte'],
  }
  if (known[paletteId]) return known[paletteId][light ? 1 : 0]
  return light ? `${paletteId}-light` : paletteId
}

function resolver(accounts, liabilities) {
  const pick = (list, label, kind) => {
    const hit = list.find((x) => x.name?.toLowerCase() === label.toLowerCase())
    if (!hit) throw new Error(`sample budget has no ${kind} named "${label}"`)
    return hit.id
  }
  return {
    account: (label) => pick(accounts, label, 'account'),
    liability: (label) => pick(liabilities, label, 'liability'),
  }
}

/**
 * The month the budget grid should open on: the newest one with a transaction
 * in it, which is where the demo data stops. Opening on today's month draws a
 * grid of em-dashes — a real state, but not one worth putting in a README.
 */
async function latestMonth(budgetId, token) {
  const given = opt('--month')
  if (given) return given
  const res = await api(`/${budgetId}/transactions?limit=1`, token)
  const rows = Array.isArray(res) ? res : (res.items ?? res.transactions ?? [])
  if (!rows.length) throw new Error('sample budget has no transactions')
  return `${rows[0].date.slice(0, 7)}-01`
}

/**
 * Scroll the page by `y`. The app scrolls an inner container, not the window,
 * so find whichever element actually has the overflow rather than assuming.
 */
async function scrollBy(page, y) {
  await page.evaluate((dy) => {
    const scrollers = [...document.querySelectorAll('body *')].filter((el) => {
      const oy = getComputedStyle(el).overflowY
      return (oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + dy
    })
    // The outermost such element is the page's own scroll region; inner ones
    // are wells (a register body, a scroll box) that would scroll alone.
    const target = scrollers.find((el) => !scrollers.some((o) => o !== el && o.contains(el)))
    if (target) target.scrollTop = dy
    else window.scrollTo(0, dy)
  }, y)
}

/**
 * Click a control by its visible label — the report range pills have no id.
 * Returns false when no such control exists: the monthly reports use a
 * months-based picker with its own labels, so a missing range pill is a shot
 * that keeps its default window, not a failed run.
 */
async function clickByText(page, label) {
  const handle = await page.evaluateHandle((text) => {
    const controls = document.querySelectorAll('button, [role="tab"], [role="button"]')
    return [...controls].find((el) => el.textContent?.trim() === text) ?? null
  }, label)
  const el = handle.asElement()
  if (!el) return false
  await el.click()
  return true
}

async function main() {
  const tokens = await login()
  const budget = await sampleBudget(tokens.access_token, { create: flag('--create-sample') })
  const [accounts, liabilities, month] = await Promise.all([
    api(`/${budget.id}/accounts`, tokens.access_token),
    api(`/${budget.id}/liabilities`, tokens.access_token).catch(() => []),
    latestMonth(budget.id, tokens.access_token),
  ])
  const refs = resolver(accounts, liabilities)

  const only = opt('--only')
  const wanted = SHOTS.filter((s) => {
    if (only) return only.split(',').includes(s.name)
    return flag('--all') || !s.extra
  })
  if (!wanted.length) throw new Error(`--only matched no shots`)

  const theme = themeFor(opt('--theme', 'catppuccin'), flag('--light'))
  await mkdir(OUT, { recursive: true })
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true })
  try {
    const page = await browser.newPage()
    await seedPage(page, tokens, budget.id, { theme, selectedMonth: month })
    // The scrollbar gutter is chrome, not product: it lands in every shot and
    // differs between machines.
    await page.evaluateOnNewDocument(() => {
      const style = document.createElement('style')
      style.textContent = '::-webkit-scrollbar { display: none }'
      document.addEventListener('DOMContentLoaded', () => document.head.append(style))
    })
    for (const shot of wanted) {
      const route = shot.route(refs)
      await page.setViewport({ ...VIEWPORT, height: shot.height ?? VIEWPORT.height })
      await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle0', timeout: 45000 })
      await new Promise((r) => setTimeout(r, SETTLE))
      let noted = ''
      if (shot.click) {
        if (await clickByText(page, shot.click)) {
          await page.waitForNetworkIdle({ timeout: 30000 }).catch(() => {})
          await new Promise((r) => setTimeout(r, SETTLE))
        } else {
          noted = `  (no "${shot.click}" control; kept the default range)`
        }
      }
      await scrollBy(page, shot.scroll ?? 0)
      await new Promise((r) => setTimeout(r, 300))
      const path = resolve(OUT, `${shot.name}.png`)
      await page.screenshot({ path })
      console.log(`ok  ${shot.name.padEnd(20)} ${route}${noted}`)
    }
  } finally {
    await browser.close()
  }
  console.log(`\n${wanted.length} shots on ${theme}, budget month ${month} → ${OUT}`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
