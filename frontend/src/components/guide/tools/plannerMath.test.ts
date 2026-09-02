import { describe, expect, it } from 'vitest'
import type { PlanPayload } from '../../../api/categoryPlans'
import {
  derivePaycheckCount,
  draftToPayload,
  evenSplitCents,
  incomeTotalCents,
  monthlyPlannedCents,
  parseCentsField,
  parseDueDayField,
  paycheckIncomeCents,
  paycheckPlannedCents,
  payloadToDraft,
  resizePaychecks,
  type DraftPaycheck,
  type PlanDraft,
} from './plannerMath'

let n = 0
const mkId = () => `id-${++n}`

function payload(over: Partial<PlanPayload> = {}): PlanPayload {
  return {
    schema_version: 1,
    monthly_income_cents: 520000,
    cadence: 'biweekly',
    paycheck_count_override: null,
    paychecks: [
      { id: 'p1', income_override_cents: null, items: [] },
      { id: 'p2', income_override_cents: null, items: [] },
    ],
    ...over,
  }
}

describe('derivePaycheckCount', () => {
  it('maps every cadence', () => {
    expect(derivePaycheckCount('weekly')).toBe(4)
    expect(derivePaycheckCount('biweekly')).toBe(2)
    expect(derivePaycheckCount('semimonthly')).toBe(2)
    expect(derivePaycheckCount('monthly')).toBe(1)
  })
})

describe('evenSplitCents', () => {
  it('gives remainder cents to the earliest paychecks', () => {
    expect(evenSplitCents(100001, 3)).toEqual([33334, 33334, 33333])
  })
  it('sums back to the total for every count', () => {
    for (let count = 1; count <= 10; count++) {
      const parts = evenSplitCents(100001, count)
      expect(parts).toHaveLength(count)
      expect(parts.reduce((a, b) => a + b, 0)).toBe(100001)
      // No slot differs from another by more than one cent.
      expect(Math.max(...parts) - Math.min(...parts)).toBeLessThanOrEqual(1)
    }
  })
  it('handles zero and single-cent totals', () => {
    expect(evenSplitCents(0, 3)).toEqual([0, 0, 0])
    expect(evenSplitCents(1, 3)).toEqual([1, 0, 0])
  })
  it('returns nothing for a nonsense count', () => {
    expect(evenSplitCents(100, 0)).toEqual([])
  })
})

describe('parseCentsField', () => {
  it('treats empty as not-entered, not zero', () => {
    expect(parseCentsField('')).toBeNull()
    expect(parseCentsField('  ')).toBeNull()
  })
  it('parses money text to cents', () => {
    expect(parseCentsField('1,234.56')).toBe(123456)
    expect(parseCentsField('0')).toBe(0)
  })
  it('flags garbage and negatives as NaN, never zero', () => {
    expect(Number.isNaN(parseCentsField('abc'))).toBe(true)
    expect(Number.isNaN(parseCentsField('-5'))).toBe(true)
  })
})

describe('parseDueDayField', () => {
  it('accepts 1–31, empty as none, rejects the rest', () => {
    expect(parseDueDayField('')).toBeNull()
    expect(parseDueDayField('1')).toBe(1)
    expect(parseDueDayField('31')).toBe(31)
    expect(Number.isNaN(parseDueDayField('0'))).toBe(true)
    expect(Number.isNaN(parseDueDayField('32'))).toBe(true)
    expect(Number.isNaN(parseDueDayField('2.5'))).toBe(true)
    expect(Number.isNaN(parseDueDayField('soon'))).toBe(true)
  })
})

describe('paycheckIncomeCents', () => {
  it('defaults to the even-split slot', () => {
    const doc = payload({
      monthly_income_cents: 100001,
      paychecks: [
        { id: 'p1', income_override_cents: null, items: [] },
        { id: 'p2', income_override_cents: null, items: [] },
        { id: 'p3', income_override_cents: null, items: [] },
      ],
    })
    expect(paycheckIncomeCents(doc, 0)).toBe(33334)
    expect(paycheckIncomeCents(doc, 2)).toBe(33333)
  })
  it('an override wins for its paycheck and leaves the others on the split', () => {
    const doc = payload({
      paychecks: [
        { id: 'p1', income_override_cents: 300000, items: [] },
        { id: 'p2', income_override_cents: null, items: [] },
      ],
    })
    expect(paycheckIncomeCents(doc, 0)).toBe(300000)
    // NOT re-split against the remainder: still take-home ÷ count.
    expect(paycheckIncomeCents(doc, 1)).toBe(260000)
  })
  it('a zero override is an override, not an absence', () => {
    const doc = payload({
      paychecks: [
        { id: 'p1', income_override_cents: 0, items: [] },
        { id: 'p2', income_override_cents: null, items: [] },
      ],
    })
    expect(paycheckIncomeCents(doc, 0)).toBe(0)
  })
})

describe('totals', () => {
  const doc = payload({
    paychecks: [
      {
        id: 'p1',
        income_override_cents: null,
        items: [
          { id: 'i1', category_id: null, name: 'Rent', due_day: 1, amount_cents: 145000 },
          { id: 'i2', category_id: null, name: 'Utilities', due_day: null, amount_cents: null },
        ],
      },
      {
        id: 'p2',
        income_override_cents: 200000,
        items: [
          { id: 'i3', category_id: null, name: 'Groceries', due_day: null, amount_cents: 45000 },
        ],
      },
    ],
  })

  it('planned ignores rows with no amount — drafts, not zeros', () => {
    expect(paycheckPlannedCents(doc.paychecks[0])).toBe(145000)
    expect(monthlyPlannedCents(doc)).toBe(190000)
  })
  it('income total reflects overrides and shows the drift', () => {
    // 260000 (split) + 200000 (override) ≠ 520000 take-home; the summary
    // strip renders exactly this difference.
    expect(incomeTotalCents(doc)).toBe(460000)
  })
  it('over-allocation goes negative rather than clamping', () => {
    const over = payload({
      monthly_income_cents: 100000,
      paychecks: [
        {
          id: 'p1',
          income_override_cents: null,
          items: [
            { id: 'i1', category_id: null, name: 'Rent', due_day: null, amount_cents: 145000 },
          ],
        },
      ],
    })
    expect(paycheckIncomeCents(over, 0) - paycheckPlannedCents(over.paychecks[0])).toBe(-45000)
  })
})

describe('resizePaychecks', () => {
  const items = (paycheck: DraftPaycheck) => paycheck.items.map((i) => i.name)
  const base: DraftPaycheck[] = [
    {
      id: 'p1',
      income: '',
      items: [{ id: 'i1', categoryId: null, name: 'Rent', dueDay: '', amount: '' }],
    },
    {
      id: 'p2',
      income: '',
      items: [{ id: 'i2', categoryId: null, name: 'Groceries', dueDay: '', amount: '' }],
    },
    {
      id: 'p3',
      income: '250',
      items: [{ id: 'i3', categoryId: null, name: 'Fun', dueDay: '', amount: '' }],
    },
  ]

  it('growing appends blank paychecks', () => {
    const { paychecks, moved } = resizePaychecks(base, 4, mkId)
    expect(paychecks).toHaveLength(4)
    expect(moved).toBe(0)
    expect(paychecks[3].items).toEqual([])
  })
  it("shrinking moves the removed paychecks' rows to the last kept one", () => {
    const { paychecks, moved } = resizePaychecks(base, 2, mkId)
    expect(paychecks).toHaveLength(2)
    expect(moved).toBe(1)
    expect(items(paychecks[1])).toEqual(['Groceries', 'Fun'])
  })
  it('shrinking to one gathers everything', () => {
    const { paychecks, moved } = resizePaychecks(base, 1, mkId)
    expect(moved).toBe(2)
    expect(items(paychecks[0])).toEqual(['Rent', 'Groceries', 'Fun'])
  })
  it('same count is a no-op returning the same array', () => {
    expect(resizePaychecks(base, 3, mkId).paychecks).toBe(base)
  })
})

describe('draft ↔ payload', () => {
  it('round-trips a full document exactly', () => {
    const doc = payload({
      paychecks: [
        {
          id: 'p1',
          income_override_cents: 300001,
          items: [
            { id: 'i1', category_id: 'c1', name: 'Rent', due_day: 1, amount_cents: 145000 },
            { id: 'i2', category_id: null, name: '', due_day: null, amount_cents: null },
          ],
        },
        { id: 'p2', income_override_cents: null, items: [] },
      ],
    })
    expect(draftToPayload(payloadToDraft(doc))).toEqual(doc)
  })
  it('serializes invalid text as null, never as zero', () => {
    const draft: PlanDraft = {
      monthlyIncome: '5200',
      cadence: 'biweekly',
      countOverride: null,
      paychecks: [
        {
          id: 'p1',
          income: 'garbage',
          items: [{ id: 'i1', categoryId: null, name: 'Rent', dueDay: '45', amount: 'oops' }],
        },
      ],
    }
    const doc = draftToPayload(draft)
    expect(doc.paychecks[0].income_override_cents).toBeNull()
    expect(doc.paychecks[0].items[0].amount_cents).toBeNull()
    expect(doc.paychecks[0].items[0].due_day).toBeNull()
  })
  it('empty monthly income stores zero and renders back as empty', () => {
    const doc = payload({ monthly_income_cents: 0 })
    expect(payloadToDraft(doc).monthlyIncome).toBe('')
    expect(draftToPayload(payloadToDraft(doc)).monthly_income_cents).toBe(0)
  })
})
