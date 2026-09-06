/**
 * The scenario panel, which exists because its own feature was unfindable.
 *
 * Extra-per-month and curtailment have shipped since v2026.09.3: the server
 * computes both, the chart draws the accelerated curve, the schedule table
 * toggles between them. The controls were two bare number boxes in the chart
 * section's header, and the person who built the feature reported that there
 * was nowhere to enter a curtailment. So what these pin is discoverability —
 * that the panel names the thing, says what each field does, and is useful
 * before anything has been typed into it.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PaydownWhatIf } from './PaydownWhatIf'

const money = (n: number) => `$${n.toFixed(2)}`

function panel(over: Partial<Parameters<typeof PaydownWhatIf>[0]> = {}) {
  return render(
    <PaydownWhatIf
      extra=""
      onExtraChange={vi.fn()}
      curtailment=""
      onCurtailmentChange={vi.fn()}
      extraPayment={0}
      curtailmentAmount={0}
      storedPlan={null}
      savings={null}
      onSavePlan={vi.fn()}
      onClearPlan={vi.fn()}
      saving={false}
      formatMoney={money}
      {...over}
    />
  )
}

describe('finding it at all', () => {
  it('asks the question in a heading', () => {
    panel()
    expect(screen.getByRole('heading', { name: /What if you paid more/i })).toBeInTheDocument()
  })

  it('writes down the word people search for', () => {
    // "I thought we had added mechanisms for curtailment payments but I
    // didn't see a place to handle that." Neither old label said it.
    panel()
    expect(screen.getByLabelText(/curtailment/i)).toBeInTheDocument()
  })

  it('says what each field does before anything is typed', () => {
    panel()
    expect(screen.getByText(/On top of the minimum/)).toBeInTheDocument()
    expect(screen.getByText(/every cent of it is principal/)).toBeInTheDocument()
    expect(screen.getByText(/Nothing is saved until you say so/)).toBeInTheDocument()
  })
})

describe('the answer', () => {
  it('reports what the extra buys', () => {
    panel({
      extra: '200',
      extraPayment: 200,
      savings: { monthsSooner: 41, interestSaved: 18450 },
    })
    expect(screen.getByText(/\+\$200\.00\/mo/)).toBeInTheDocument()
    expect(screen.getByText(/41 months sooner/)).toBeInTheDocument()
    expect(screen.getByText(/\$18450\.00 less interest/)).toBeInTheDocument()
  })

  it('reports a one-off and a monthly extra together', () => {
    panel({
      extra: '200',
      curtailment: '5000',
      extraPayment: 200,
      curtailmentAmount: 5000,
      savings: { monthsSooner: 60, interestSaved: 31000 },
    })
    expect(screen.getByText(/\+\$200\.00\/mo and \$5000\.00 once/)).toBeInTheDocument()
  })

  it('says "actually pays off" when the baseline never does', () => {
    // There is no "sooner" than never; the old copy would have said NaN.
    panel({
      extra: '200',
      extraPayment: 200,
      savings: { monthsSooner: null, interestSaved: 900 },
    })
    expect(screen.getByText(/actually pays off/)).toBeInTheDocument()
  })

  it('is honest when even the extra does not clear the debt', () => {
    panel({ extra: '5', extraPayment: 5, savings: null })
    expect(screen.getByText(/not covering the interest/)).toBeInTheDocument()
  })

  it('sends you to the terms when there is nothing to project from', () => {
    panel({ disabled: true })
    expect(screen.getByText(/APR and minimum payment/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Extra every month/)).toBeDisabled()
  })
})

describe('saving it as a plan', () => {
  it('offers to keep a monthly extra', async () => {
    const onSavePlan = vi.fn()
    panel({
      extra: '200',
      extraPayment: 200,
      savings: { monthsSooner: 4, interestSaved: 10 },
      onSavePlan,
    })
    await userEvent.click(screen.getByRole('button', { name: 'Save as my plan' }))
    expect(onSavePlan).toHaveBeenCalled()
  })

  it('shows the stored plan as stored, with a way out', () => {
    panel({
      extra: '200',
      extraPayment: 200,
      storedPlan: 200,
      savings: { monthsSooner: 4, interestSaved: 10 },
    })
    expect(screen.getByText(/This is your plan/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save as my plan' })).not.toBeInTheDocument()
  })

  it('offers to save again once the figure differs from the plan', () => {
    panel({
      extra: '300',
      extraPayment: 300,
      storedPlan: 200,
      savings: { monthsSooner: 6, interestSaved: 20 },
    })
    expect(screen.getByRole('button', { name: 'Save as my plan' })).toBeInTheDocument()
  })

  it('does not call a one-off "your plan" — a plan is what repeats', () => {
    panel({
      extra: '200',
      curtailment: '5000',
      extraPayment: 200,
      curtailmentAmount: 5000,
      storedPlan: 200,
      savings: { monthsSooner: 30, interestSaved: 900 },
    })
    expect(screen.queryByText(/This is your plan/)).not.toBeInTheDocument()
  })
})

describe('typing', () => {
  it('reports each keystroke to its owner', async () => {
    const onExtraChange = vi.fn()
    panel({ onExtraChange })
    await userEvent.type(screen.getByLabelText(/Extra every month/), '5')
    expect(onExtraChange).toHaveBeenCalledWith('5')
  })
})
