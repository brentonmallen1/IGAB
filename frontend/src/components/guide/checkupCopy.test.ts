import { describe, it, expect } from 'vitest'
import type { CheckupFinding, CheckupMetric, FindingKind } from '../../api/guide'
import {
  checkCopyIntegrity,
  FINDING_TONE,
  findingTone,
  formatMetricTarget,
  formatMetricValue,
  formatMoneyLine,
  metricProgress,
  metricStatus,
  METRIC_KEYS,
} from './checkupCopy'

const fmt = { formatMoney: (n: number) => `$${n}` }

function metric(over: Partial<CheckupMetric>): CheckupMetric {
  return { key: 'emergency_fund', label: 'Emergency fund', value: '1.8', target: '3', unit: 'months', detail: '', finding_kinds: [], report: null, names: [], money_value: null, money_target: null, ...over }
}

function finding(kind: FindingKind): CheckupFinding {
  return { kind, rank: 1, concept_key: null, title: kind, detail: '', value: null, target: null, names: [] }
}

describe('checkup copy', () => {
  it('every explainer is complete and points at content that exists', () => {
    expect(checkCopyIntegrity()).toEqual([])
    expect(METRIC_KEYS.length).toBe(8)
  })

  it('status: a fired finding wins, then the figure against its target', () => {
    expect(metricStatus(metric({}), finding('ef_below_starter'))).toEqual({ status: 'warn', text: 'worth a look' })
    expect(metricStatus(metric({ value: null }))).toEqual({ status: 'unknown', text: 'not known' })
    expect(metricStatus(metric({ value: '4' }))).toEqual({ status: 'good', text: 'on target' })
    expect(metricStatus(metric({ key: 'high_interest_debt', value: '0', target: '0', unit: 'money' })).text).toBe('none')
    expect(metricStatus(metric({ key: 'categories_funded', value: '18', target: '21', unit: 'count' })).text).toBe('3 underfunded')
    expect(metricStatus(metric({ key: 'categories_funded', value: '21', target: '21', unit: 'count' })).text).toBe('all funded')
  })

  it('only an emergency fund that has not started speaks in red', () => {
    expect(metricStatus(metric({ value: '0' }), finding('ef_not_started'))).toEqual({ status: 'danger', text: 'not started' })
    const kinds = Object.keys(FINDING_TONE) as FindingKind[]
    expect(kinds.filter((k) => findingTone(k) === 'danger')).toEqual(['ef_not_started'])
    expect(findingTone('stale_external')).toBe('warn')
  })

  it('says what the months are worth, when the row carries the money', () => {
    const row = metric({ value: '0.38', money_value: '1240', money_target: '9720' })
    expect(formatMoneyLine(row, fmt, { emergency_fund_months: 3 })).toBe('$1240 of $9720 — three months of essentials')
    expect(formatMoneyLine(row, fmt, {})).toBe('$1240 of $9720 — three months of essentials')
    expect(formatMoneyLine(metric({}), fmt, { emergency_fund_months: 3 })).toBeNull()
  })

  it('progress only where a bar means something', () => {
    expect(metricProgress(metric({}))).toBeCloseTo(0.6)
    expect(metricProgress(metric({ value: '9' }))).toBe(1)
    expect(metricProgress(metric({ key: 'high_interest_debt', value: '3410', target: '0' }))).toBeNull()
    expect(metricProgress(metric({ value: null }))).toBeNull()
  })

  it('formats values and targets by unit', () => {
    expect(formatMetricValue(metric({}), fmt)).toBe('1.8 mo')
    expect(formatMetricValue(metric({ unit: 'percent', value: '11.4' }), fmt)).toBe('11.4%')
    expect(formatMetricValue(metric({ unit: 'money', value: '3410' }), fmt)).toBe('$3410')
    expect(formatMetricValue(metric({ value: null }), fmt)).toBe('—')
    expect(formatMetricTarget(metric({}), fmt, { emergency_fund_months: 3, emergency_fund_months_high: 6 })).toBe('target 3–6 months')
    expect(formatMetricTarget(metric({ key: 'high_interest_debt', unit: 'money', target: '0' }), fmt, {})).toBe('target: none')
    expect(formatMetricTarget(metric({ key: 'categories_funded', unit: 'count', target: '21' }), fmt, {})).toBe('of 21 with targets')
    expect(formatMetricTarget(metric({ unit: 'money', target: '1000' }), fmt, {})).toBe('target $1000 to start')
  })
})
