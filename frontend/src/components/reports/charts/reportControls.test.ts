import { describe, expect, it } from 'vitest'
import shared from '../../../../../shared/report_controls.json'
import {
  HORIZON_OPTIONS,
  PAYDAY_WINDOW_OPTIONS,
  PAYEE_RANKED,
  SENSITIVITY_OPTIONS,
  TIMELINE_LIMITS,
} from './reportControls'

function sharedValues(path: string, param: string): number[] {
  const control = shared.controls.find((c) => c.path === path && c.param === param)
  if (!control) throw new Error(`shared/report_controls.json has no ${path}?${param}`)
  return control.values
}

describe('the report controls are the list the server is tested against', () => {
  it.each([
    ['cash-projection', 'days', [...HORIZON_OPTIONS]],
    ['payday-effect', 'window', [...PAYDAY_WINDOW_OPTIONS]],
    ['large-transactions', 'limit', [...TIMELINE_LIMITS]],
    ['anomalies', 'threshold', SENSITIVITY_OPTIONS.map((o) => o.value)],
    ['payee-analysis', 'limit', [PAYEE_RANKED]],
  ])('%s?%s', (path, param, values) => {
    expect(values).toEqual(sharedValues(path, param))
  })

  it('names no control the UI does not have', () => {
    expect(shared.controls).toHaveLength(5)
  })
})
