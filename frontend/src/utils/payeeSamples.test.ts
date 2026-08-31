import { describe, it, expect } from 'vitest'
import cases from '../../../shared/sample_cases.json'
import { dedupeSamples, samplesFromLines } from './payeeSamples'

describe('dedupeSamples', () => {
  // The same cases the backend runs in test_payee_names.py.
  for (const c of cases.cases) {
    it(c.note || JSON.stringify(c.parts), () => {
      expect(dedupeSamples(c.parts)).toEqual(c.samples)
    })
  }
})

describe('samplesFromLines', () => {
  it('reads one sample per line and keeps a comma inside a line', () => {
    expect(
      samplesFromLines('NORTHWIND PAYROLL\r\n\n  NORTHWIND … DOE, JANE \nnorthwind payroll')
    ).toEqual(['NORTHWIND PAYROLL', 'NORTHWIND … DOE, JANE'])
  })
})
