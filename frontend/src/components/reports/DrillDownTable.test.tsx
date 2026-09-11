/**
 * The footer is the sum of the rows above it.
 *
 * `total` was a free-form prop with no relation to `rows`, and two of the
 * three callers passing it handed over a WIDER set: Budget vs Actual passed
 * the period's whole spend while "Overspent only" was ticked, and Payee
 * Analysis passed every payee's total beside its top-20 slice. The row headed
 * Total was then larger than the column above it — the one number on this
 * table a reader can check on paper.
 *
 * Fixed in the component rather than at each call site, so a new caller
 * cannot reintroduce it: there is no prop that sets the total any more.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DrillDownTable } from './DrillDownTable'

const rows = [
  { id: 'a', name: 'Harborstone Realty', amount: 400 },
  { id: 'b', name: 'Cascade Grocers', amount: 300 },
]

function cellsOf(label: string): string[] {
  const row = screen.getByText(label).closest('tr')
  return Array.from(row?.querySelectorAll('td') ?? []).map((td) => td.textContent ?? '')
}

describe('DrillDownTable', () => {
  it('totals the rows it drew, whatever wider set they came from', () => {
    render(
      <DrillDownTable
        rows={rows}
        wider={{ total: 1050, count: 5, label: 'payees' }}
        amountLabel="Spent"
      />
    )
    // $700, not the $1,050 the old `total` prop would have printed here.
    expect(cellsOf('Total of the 2 shown')).toContain('$700.00')
    expect(cellsOf('of $1,050.00 across 5 payees')).toContain('$1,050.00')
  })

  it('says plain "Total" when the rows are the whole set', () => {
    render(<DrillDownTable rows={rows} wider={{ total: 700, label: 'payees' }} />)
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.queryByText(/of \$/)).toBeNull()
  })

  it('draws a total even with no wider set to compare against', () => {
    render(<DrillDownTable rows={rows} />)
    expect(cellsOf('Total')).toContain('$700.00')
  })

  it("states the shown rows' share only in a column of shares", () => {
    // Budget vs Actual fills `pct` with each row's variance, and the wider
    // row's share of spend landed in that column: -25.0% and -40.0% above a
    // 23.4% that read as the set's aggregate variance.
    const variance = [
      { id: 'd', name: 'Dining', amount: 500, pct: -25 },
      { id: 'g', name: 'Groceries', amount: 670, pct: -40 },
    ]
    const wider = { total: 5000, count: 40, label: 'categories' }
    const { unmount } = render(<DrillDownTable rows={variance} wider={wider} />)
    expect(cellsOf('of $5,000.00 across 40 categories')).toEqual([
      'of $5,000.00 across 40 categories',
      '$5,000.00',
      '',
    ])
    unmount()

    render(<DrillDownTable rows={variance} wider={wider} pctIsShare />)
    expect(cellsOf('of $5,000.00 across 40 categories')).toContain('23.4%')
  })

  it('keeps a negative row negative', () => {
    // Income vs Expenses lists monthly expenses; a month whose refunds beat
    // its spending is negative, and the table's `Math.abs` drew "we got $40
    // back" as "we spent $40".
    render(
      <DrillDownTable
        rows={[
          { id: 'sep', name: 'Sep', amount: 120 },
          { id: 'oct', name: 'Oct', amount: -40 },
        ]}
        amountLabel="Expenses"
      />
    )
    expect(cellsOf('Oct')).toContain('-$40.00')
    expect(cellsOf('Total')).toContain('$80.00')
  })
})
