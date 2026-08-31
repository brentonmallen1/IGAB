import { describe, expect, it } from 'vitest'
import type { CashFlowReport } from '../../../types'
import { buildSankeyView, deltaColor, extractPrevTotals, formatDelta } from './sankeyView'

const fmt = (n: number) => `$${n.toFixed(0)}`

function report(): CashFlowReport {
  return {
    nodes: [
      { id: '__budget__', name: 'Budget', type: 'budget' },
      { id: 'inc_p1', name: 'Employer', type: 'income_payee' },
      { id: 'g_1', name: 'Everyday', type: 'category_group' },
      { id: 'g_2', name: 'Home', type: 'category_group' },
      { id: 'c_1', name: 'Groceries', type: 'category' },
      { id: 'c_2', name: 'Gas', type: 'category' },
      { id: 'c_3', name: 'Rent', type: 'category' },
    ],
    links: [
      { source: 'inc_p1', target: '__budget__', value: 3000 },
      { source: '__budget__', target: 'g_1', value: 400 },
      { source: '__budget__', target: 'g_2', value: 600 },
      { source: 'g_1', target: 'c_1', value: 300 },
      { source: 'g_1', target: 'c_2', value: 100 },
      { source: 'g_2', target: 'c_3', value: 600 },
    ],
    total_income: 3000,
    total_expense: 1000,
    total_spending: 1000,
    total_savings: 0,
    total_debt_principal: 0,
    category_payees: {
      c_1: [
        { name: 'MegaMart', total: 250 },
        { name: 'CornerStore', total: 50 },
      ],
    },
    group_categories: { g_1: [{ name: 'Groceries', total: 300 }] },
  }
}

describe('buildSankeyView', () => {
  it('level 1 shows Income → every group', () => {
    const view = buildSankeyView(report(), null, null, null, undefined)
    expect(view.sankeyData.nodes.map((n) => n.id)).toEqual(['__income__', 'g_1', 'g_2'])
    expect(view.sankeyData.links).toEqual([
      { source: 0, target: 1, value: 400 },
      { source: 0, target: 2, value: 600 },
    ])
  })

  it('level 2 shows Income → group → its categories only', () => {
    const view = buildSankeyView(report(), 'g_1', null, null, undefined)
    expect(view.sankeyData.nodes.map((n) => n.id)).toEqual(['__income__', 'g_1', 'c_1', 'c_2'])
    expect(view.sankeyData.links).toEqual([
      { source: 0, target: 1, value: 400 },
      { source: 1, target: 2, value: 300 },
      { source: 1, target: 3, value: 100 },
    ])
  })

  it('level 3 shows the category fan-out to payees', () => {
    const view = buildSankeyView(report(), 'g_1', 'c_1', null, undefined)
    expect(view.sankeyData.nodes.map((n) => n.name)).toEqual([
      'Income',
      'Everyday',
      'Groceries',
      'MegaMart',
      'CornerStore',
    ])
    expect(view.sankeyData.links.map((l) => l.value)).toEqual([400, 300, 250, 50])
  })

  it('drops zero-value links', () => {
    const data = report()
    data.links = data.links.map((l) => (l.target === 'g_2' ? { ...l, value: 0 } : l))
    const view = buildSankeyView(data, null, null, null, undefined)
    expect(view.sankeyData.links).toEqual([{ source: 0, target: 1, value: 400 }])
  })

  it('is empty for missing or empty data', () => {
    expect(buildSankeyView(undefined, null, null, null, undefined).sankeyData.nodes).toEqual([])
    const empty = { ...report(), nodes: [] }
    expect(buildSankeyView(empty, null, null, null, undefined).sankeyData.nodes).toEqual([])
  })

  it('attaches previous-window values by stable id, null for new nodes', () => {
    const prev = report()
    // Previous window had different totals and no Home group at all
    prev.nodes = prev.nodes.filter((n) => n.id !== 'g_2' && n.id !== 'c_3')
    prev.links = [
      { source: 'inc_p1', target: '__budget__', value: 2000 },
      { source: '__budget__', target: 'g_1', value: 350 },
      { source: 'g_1', target: 'c_1', value: 300 },
      { source: 'g_1', target: 'c_2', value: 50 },
    ]
    const prevTotals = extractPrevTotals(prev)
    const view = buildSankeyView(report(), null, null, prevTotals, prev)

    const byId = new Map(view.sankeyData.nodes.map((n) => [n.id, n]))
    expect(byId.get('g_1')?.prev).toBe(350)
    expect(byId.get('g_2')?.prev).toBeNull() // new this window
    expect(byId.get('__income__')?.prev).toBeUndefined() // income delta lives elsewhere
  })

  it('matches previous payees by name at level 3', () => {
    const prev = report()
    prev.category_payees = { c_1: [{ name: 'MegaMart', total: 200 }] }
    const view = buildSankeyView(report(), 'g_1', 'c_1', extractPrevTotals(prev), prev)
    const byName = new Map(view.sankeyData.nodes.map((n) => [n.name, n]))
    expect(byName.get('MegaMart')?.prev).toBe(200)
    expect(byName.get('CornerStore')?.prev).toBeNull()
  })
})

describe('extractPrevTotals', () => {
  it('splits budget→group and group→category link totals', () => {
    const { groups, cats } = extractPrevTotals(report())
    expect(groups.get('g_1')).toBe(400)
    expect(groups.get('g_2')).toBe(600)
    expect(cats.get('c_1')).toBe(300)
    expect(cats.get('c_3')).toBe(600)
    // income links belong to neither bucket
    expect(groups.has('__budget__')).toBe(false)
  })
})

describe('formatDelta', () => {
  it('formats signed amount with percent', () => {
    expect(formatDelta(120, 100, fmt)).toBe('+$20 (+20%)')
    expect(formatDelta(80, 100, fmt)).toBe('−$20 (−20%)')
  })

  it('omits the percent when prev is 0', () => {
    expect(formatDelta(50, 0, fmt)).toBe('+$50')
  })
})

describe('deltaColor', () => {
  it('more income is good; more spending is bad', () => {
    expect(deltaColor(120, 100, 'income')).toBe('var(--color-positive)')
    expect(deltaColor(120, 100, 'category')).toBe('var(--color-negative)')
    expect(deltaColor(80, 100, 'category')).toBe('var(--color-positive)')
  })
})
