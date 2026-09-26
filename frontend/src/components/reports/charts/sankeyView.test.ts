import { describe, expect, it } from 'vitest'
import type { CashFlowReport } from '../../../types'
import {
  HUB,
  buildSankeyView,
  categoryNodeDrill,
  deltaColor,
  extractPrevTotals,
  formatDelta,
  sankeyExportRows,
  sankeyGeometry,
  sankeyHeight,
} from './sankeyView'

const fmt = (n: number) => `$${n.toFixed(0)}`

/** As the server draws it (`domain/cash_flow.py`): two sources into the hub,
 *  two groups and Left over out of it — 3000 + 100 in, 1000 + 2100 out. */
function report(): CashFlowReport {
  return {
    nodes: [
      { id: HUB, name: 'Budget', type: 'budget' },
      { id: 'inc_p1', name: 'Northwind Payserv', type: 'income_payee' },
      { id: 'drawn_refunds', name: 'Refunds', type: 'inflow' },
      { id: 'g_1', name: 'Everyday', type: 'category_group' },
      { id: 'g_2', name: 'Home', type: 'category_group' },
      { id: 'g___left_over__', name: 'Left over', type: 'left_over' },
      { id: 'c_1', name: 'Groceries', type: 'category', entity_id: 'cat-1' },
      { id: 'c_2', name: 'Gas', type: 'category', entity_id: 'cat-2' },
      { id: 'c_3', name: 'Rent', type: 'category', entity_id: 'cat-3' },
    ],
    links: [
      { source: 'inc_p1', target: HUB, value: 3000 },
      { source: 'drawn_refunds', target: HUB, value: 100 },
      { source: HUB, target: 'g_1', value: 400 },
      { source: HUB, target: 'g_2', value: 600 },
      { source: HUB, target: 'g___left_over__', value: 2100 },
      { source: 'g_1', target: 'c_1', value: 300 },
      { source: 'g_1', target: 'c_2', value: 100 },
      { source: 'g_2', target: 'c_3', value: 600 },
    ],
    total_income: 3000,
    total_expense: 1000,
    total_spending: 900,
    total_savings: 0,
    total_debt_principal: 0,
    total_assigned: null,
    net: 2100,
    category_payees: {
      c_1: [
        { name: 'MegaMart', total: 250 },
        { name: 'CornerStore', total: 70 },
      ],
    },
    group_categories: { g_1: [{ name: 'Groceries', total: 300 }] },
    category_returns: { c_1: { name: 'Refunds', total: 20 } },
  }
}

const idsOf = (view: ReturnType<typeof buildSankeyView>) => view.sankeyData.nodes.map((n) => n.id)

describe('buildSankeyView', () => {
  it('draws the served sources, not one Income node sized to the outflows', () => {
    // The client drew a single "Income" node as wide as the spending — twice
    // the month's real income in the window that surfaced it.
    const view = buildSankeyView(report(), null, null, null, undefined)
    expect(idsOf(view)).toEqual(['inc_p1', 'drawn_refunds', HUB, 'g_1', 'g_2', 'g___left_over__'])
    expect(view.sankeyData.links).toEqual([
      { source: 0, target: 2, value: 3000 },
      { source: 1, target: 2, value: 100 },
      { source: 2, target: 3, value: 400 },
      { source: 2, target: 4, value: 600 },
      { source: 2, target: 5, value: 2100 },
    ])
  })

  it('balances: what enters the hub leaves it', () => {
    const { links } = buildSankeyView(report(), null, null, null, undefined).sankeyData
    const hub = 2
    const sum = (pick: (l: { source: number; target: number }) => boolean) =>
      links.filter(pick).reduce((s, l) => s + l.value, 0)
    expect(sum((l) => l.target === hub)).toBe(sum((l) => l.source === hub))
  })

  it('a group shows Budget → group → its categories only', () => {
    const view = buildSankeyView(report(), 'g_1', null, null, undefined)
    expect(view.sankeyData.nodes.map((n) => n.name)).toEqual([
      'Budget',
      'Everyday',
      'Groceries',
      'Gas',
    ])
    expect(view.sankeyData.links).toEqual([
      { source: 0, target: 1, value: 400 },
      { source: 1, target: 2, value: 300 },
      { source: 1, target: 3, value: 100 },
    ])
  })

  it('a category fans out to payees, with what came back as a source', () => {
    // Payees net to 320 against a 300 category: 20 was refunded by a payee
    // with no charge in the window. Without the source the level is lopsided.
    const view = buildSankeyView(report(), 'g_1', 'c_1', null, undefined)
    expect(view.sankeyData.nodes.map((n) => n.name)).toEqual([
      'Budget',
      'Everyday',
      'Groceries',
      'Refunds',
      'MegaMart',
      'CornerStore',
    ])
    expect(view.sankeyData.links.map((l) => [l.source, l.target, l.value])).toEqual([
      [0, 1, 400],
      [1, 2, 300],
      [3, 2, 20],
      [2, 4, 250],
      [2, 5, 70],
    ])
  })

  it('carries the entity id and classes a drill needs', () => {
    const view = buildSankeyView(report(), 'g_1', null, null, undefined)
    expect(view.sankeyData.nodes[2]).toMatchObject({ id: 'c_1', entity_id: 'cat-1' })
  })

  it('drops zero-value links', () => {
    const data = report()
    data.links = data.links.map((l) => (l.target === 'g_2' ? { ...l, value: 0 } : l))
    const view = buildSankeyView(data, null, null, null, undefined)
    expect(view.sankeyData.links.some((l) => l.value === 0)).toBe(false)
  })

  it('is empty for missing or empty data', () => {
    expect(buildSankeyView(undefined, null, null, null, undefined).sankeyData.nodes).toEqual([])
    const empty = { ...report(), nodes: [] }
    expect(buildSankeyView(empty, null, null, null, undefined).sankeyData.nodes).toEqual([])
  })

  it('attaches previous-window values by stable id, null for new nodes', () => {
    const prev = report()
    prev.nodes = prev.nodes.filter((n) => n.id !== 'g_2' && n.id !== 'c_3')
    prev.links = [
      { source: 'inc_p1', target: HUB, value: 2000 },
      { source: HUB, target: 'g_1', value: 350 },
      { source: HUB, target: 'g___left_over__', value: 1650 },
      { source: 'g_1', target: 'c_1', value: 300 },
      { source: 'g_1', target: 'c_2', value: 50 },
    ]
    const view = buildSankeyView(report(), null, null, extractPrevTotals(prev), prev)

    const byId = new Map(view.sankeyData.nodes.map((n) => [n.id, n]))
    expect(byId.get('inc_p1')?.prev).toBe(2000)
    expect(byId.get('drawn_refunds')?.prev).toBeNull() // new this window
    expect(byId.get('g_1')?.prev).toBe(350)
    expect(byId.get('g_2')?.prev).toBeNull()
    expect(byId.get('g___left_over__')?.prev).toBe(1650)
    expect(byId.get(HUB)?.prev).toBeUndefined() // the hub's delta lives on the cards
  })

  it('matches previous payees by name at the payee level', () => {
    const prev = report()
    prev.category_payees = { c_1: [{ name: 'MegaMart', total: 200 }] }
    const view = buildSankeyView(report(), 'g_1', 'c_1', extractPrevTotals(prev), prev)
    const byName = new Map(view.sankeyData.nodes.map((n) => [n.name, n]))
    expect(byName.get('MegaMart')?.prev).toBe(200)
    expect(byName.get('CornerStore')?.prev).toBeNull()
    expect(byName.get('Refunds')?.prev).toBeUndefined()
  })
})

describe('extractPrevTotals', () => {
  it('splits source, group and category link totals', () => {
    const { sources, groups, cats } = extractPrevTotals(report())
    expect(sources.get('inc_p1')).toBe(3000)
    expect(groups.get('g_1')).toBe(400)
    expect(groups.get('g___left_over__')).toBe(2100)
    expect(cats.get('c_1')).toBe(300)
    expect(cats.get('c_3')).toBe(600)
  })
})

describe('sankeyGeometry', () => {
  it('leaves a phone most of its width for the diagram', () => {
    // Fixed margins of 100 and 200 left a 390px phone about 90px of diagram.
    const { left, right } = sankeyGeometry(358)
    expect(358 - left - right).toBeGreaterThan(170)
  })

  it('caps the margins on a wide screen', () => {
    expect(sankeyGeometry(1400)).toMatchObject({ left: 170, right: 190 })
  })

  it('never truncates a label to nothing', () => {
    expect(sankeyGeometry(200).labelChars).toBeGreaterThanOrEqual(8)
  })
})

describe('sankeyExportRows', () => {
  it('has income links that add up to its TOTAL income row', () => {
    // The server drew fifteen sources and dropped the rest, so the export's
    // income links summed short of its total.
    const rows = sankeyExportRows(report())
    const income = rows
      .filter((r) => r.target === 'Budget' && r.source === 'Northwind Payserv')
      .reduce((s, r) => s + Number(r.value), 0)
    const total = rows.find((r) => r.source === 'TOTAL' && r.target === 'income')
    expect(income).toBe(total?.value)
  })

  it('states both sides and the net, which balance', () => {
    const rows = sankeyExportRows(report())
    const total = (target: string) => rows.find((r) => r.source === 'TOTAL' && r.target === target)
    expect(total('money in')?.value).toBe(3100)
    expect(total('money out')?.value).toBe(3100)
    expect(total('net')?.value).toBe(2100)
    expect(total('assigned')).toBeUndefined()
  })
})

describe('formatDelta', () => {
  it('formats signed amount with percent', () => {
    expect(formatDelta(120, 100, fmt, false)).toBe('+$20 (+20%)')
    expect(formatDelta(80, 100, fmt, false)).toBe('−$20 (−20%)')
  })

  it('omits the percent when prev is 0', () => {
    expect(formatDelta(50, 0, fmt, false)).toBe('+$50')
  })

  it('is the mask alone in privacy mode, with no sign or percent outside it', () => {
    // It read "−$•••• (−30%)" on Cash Flow's node labels and cards: which way
    // spending moved, and by how much, beside cards reading "$••••".
    const masked = () => '$••••'
    expect(formatDelta(70, 100, masked, true)).toBe('$••••')
    expect(formatDelta(130, 100, masked, true)).toBe('$••••')
    expect(formatDelta(50, 0, masked, true)).toBe('$••••')
  })
})

describe('deltaColor', () => {
  it('more income or more left over is good; more of anything else is not', () => {
    expect(deltaColor(120, 100, 'income_payee')).toBe('var(--color-positive)')
    expect(deltaColor(120, 100, 'left_over')).toBe('var(--color-positive)')
    expect(deltaColor(120, 100, 'category')).toBe('var(--color-negative)')
    expect(deltaColor(120, 100, 'shortfall')).toBe('var(--color-negative)')
    expect(deltaColor(80, 100, 'category')).toBe('var(--color-positive)')
  })
})

describe('categoryNodeDrill', () => {
  const window = { startDate: '2026-08-01', endDate: '2026-08-31' }

  // The three pseudo-nodes share "no category" and differ only by class. Each
  // used to drill with `uncategorized: true` alone and open the union of all
  // three — a $500 Savings node listing $1,580.
  it.each([
    ['To savings accounts', ['savings']],
    ['Debt Payments', ['debt_principal']],
    ['Uncategorized', ['spending']],
  ])('%s lists only its own classes, by the absence of a category', (name, classes) => {
    expect(categoryNodeDrill({ name, entity_id: null, activity_classes: classes }, window)).toEqual(
      {
        kind: 'category',
        label: name,
        scope: 'leaf',
        categoryIds: undefined,
        noCategory: true,
        activityClasses: classes,
        ...window,
      }
    )
  })

  it('lists both directions, because the node is net of refunds', () => {
    const drill = categoryNodeDrill(
      { name: 'Groceries', entity_id: 'cat-1', activity_classes: ['spending'] },
      window
    )
    expect(drill.direction).toBeUndefined()
  })

  it('scopes a real category by its entity id and its classes', () => {
    // One category can hang under its own group AND the savings trunk; the
    // two nodes share an entity id and differ by class.
    const drill = categoryNodeDrill(
      { name: 'Groceries', entity_id: 'cat-1', activity_classes: ['savings'] },
      window
    )
    expect(drill.categoryIds).toEqual(['cat-1'])
    expect(drill.noCategory).toBeUndefined()
    expect(drill.activityClasses).toEqual(['savings'])
  })
})

describe('sankeyHeight', () => {
  const fan = (n: number) => ({
    nodes: Array.from({ length: n + 1 }, (_, i) => i),
    // One source fanning out to n groups: the tallest column holds n.
    links: Array.from({ length: n }, (_, i) => ({ source: 0, target: i + 1, value: 1 })),
  })

  it('keeps the base height for a few nodes', () => {
    expect(sankeyHeight(fan(4), 500, false)).toBe(500)
  })

  it('grows so fifteen groups each have room for a label', () => {
    // At 500px the small groups' two-line labels printed over each other.
    expect(sankeyHeight(fan(15), 500, false)).toBe(15 * (28 + 12) + 24)
  })

  it('leaves room for the delta line when comparing', () => {
    expect(sankeyHeight(fan(15), 500, true)).toBeGreaterThan(sankeyHeight(fan(15), 500, false))
  })
})
