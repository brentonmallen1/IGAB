/**
 * Shared browser-harness plumbing for the scripts that drive a real IGAB
 * against a real Chrome: argument parsing, the API login, finding the sample
 * budget, and seeding a page's localStorage so it loads signed in.
 *
 * Both consumers (mobile-sweep, screenshots) need every one of these and none
 * of them may drift: a second copy of `sampleBudget` is a second answer to
 * "is it safe to point a camera at this budget", which is the one question
 * here that must have a single answer.
 */
const args = process.argv.slice(2)

export const flag = (name) => args.includes(name)
export const opt = (name, fallback) => {
  const i = args.indexOf(name)
  return i >= 0 ? args[i + 1] : fallback
}

export const BASE = process.env.IGAB_URL ?? 'http://localhost:5173'
export const API = process.env.IGAB_API ?? `${BASE}/api/v1`
export const CHROME =
  process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

/** Log in and return the token pair. Falls back to the .env admin account. */
export async function login() {
  const user = process.env.IGAB_USER ?? process.env.ADMIN_EMAIL
  const pass = process.env.IGAB_PASS ?? process.env.ADMIN_PASSWORD
  if (!user || !pass) throw new Error('Set IGAB_USER and IGAB_PASS (or ADMIN_EMAIL/ADMIN_PASSWORD)')
  const res = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: user, password: pass }),
  })
  if (!res.ok) throw new Error(`login failed: ${res.status}`)
  return res.json()
}

export async function api(path, token) {
  const res = await fetch(`${API}${path}`, { headers: { authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error(`${path}: ${res.status}`)
  return res.json()
}

/**
 * The sample budget, and only ever the sample budget.
 *
 * Never point a camera at a real one by accident: screenshots and sweep
 * reports carry payee names and amounts, and this repository is public. With
 * no sample budget present, either make one (`create: true` — the full demo,
 * so liabilities and assets have pages) or stop.
 */
export async function sampleBudget(token, { create = false } = {}) {
  const budgets = await api('/budgets', token)
  const found = budgets.find((b) => b.name?.toLowerCase().includes('sample'))
  if (found) return found
  if (!create) throw new Error('no sample budget; pass --create-sample to make one')
  const res = await fetch(`${API}/budgets/create-sample`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({ tier: 'full' }),
  })
  if (!res.ok) throw new Error(`create-sample failed: ${res.status}`)
  return (await res.json()).budget
}

/**
 * Seed a page so every navigation loads signed in, on the sample budget, and
 * on the requested theme. `state` merges into the persisted `igab-app` store,
 * which is where the theme lives.
 */
export async function seedPage(page, tokens, budgetId, state = {}) {
  await page.evaluateOnNewDocument(
    (t, id, extra) => {
      localStorage.setItem('access_token', t.access_token)
      localStorage.setItem('refresh_token', t.refresh_token)
      const key = 'igab-app'
      const cur = JSON.parse(localStorage.getItem(key) || '{"state":{},"version":1}')
      cur.state = { ...cur.state, currentBudgetId: id, autoOpenLastBudget: true, ...extra }
      localStorage.setItem(key, JSON.stringify(cur))
      if (extra.theme) document.documentElement.setAttribute('data-theme', extra.theme)
    },
    tokens,
    budgetId,
    state
  )
}
