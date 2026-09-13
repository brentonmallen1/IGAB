/**
 * The modal is the single home for type explanations, and — in the import
 * context — for what leaving an account out costs.
 *
 * That second part exists because nothing connected the choice to its
 * consequence: dropping an account is what produces the "1,117 transfers
 * couldn't be matched" warning, and that warning arrived as a toast long after
 * the decision was made, with no way back to it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AccountTypeInfoModal } from './AccountTypeInfoModal'
import { useMoneyRules, type MoneyShape, type MoveExplanation } from '../../api/moneyRules'

vi.mock('../../api/moneyRules', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/moneyRules')>()),
  useMoneyRules: vi.fn(),
}))

function explained(class_label: string, delta: number): MoveExplanation {
  return {
    category_role: null,
    category_applied: true,
    legs: [
      {
        role: 'from',
        on_budget: true,
        amount: -1000,
        category: 'none',
        cls: 'x',
        class_label,
        reason: 'r',
        reason_text: '',
        counted_in: [],
        planned_spend_by_tag: false,
      },
    ],
    budget_terms: delta ? [{ term: 'ready_to_assign', delta }] : [],
    class_totals: {},
    figures: {
      income: 0,
      spending: 0,
      cost_of_living: 0,
      savings: 0,
      debt_principal: 0,
      savings_rate: null,
      savings_rate_with_debt: null,
    },
    net_worth_delta: 0,
    assumption: '',
  }
}

// Invented wording on purpose: the lines must be what the server served,
// not copy the modal carries itself.
const SERVED_SHAPE: MoneyShape = {
  key: 'tracked_asset',
  label: 'Tracked account that does not count as savings',
  classification: 'asset',
  on_budget: false,
  counts_as_savings: false,
  money_in: { description: 'Served buying line', explanation: explained('Spending', -1000) },
  money_out: { description: 'Served selling line', explanation: explained('Income', 1000) },
}

const OTHER_ASSET = {
  key: 'other_asset',
  label: 'Other asset',
  classification: 'asset' as const,
  default_on_budget: false,
  default_counts_as_savings: false,
  description: 'A thing you own',
}

beforeEach(() => {
  vi.mocked(useMoneyRules).mockReturnValue({
    data: { rules: [], report_families: [], shapes: [SERVED_SHAPE], planned_spend_tag_keys: [] },
  } as unknown as ReturnType<typeof useMoneyRules>)
})

describe('AccountTypeInfoModal', () => {
  it('explains the built-in types when no registry is passed', () => {
    render(<AccountTypeInfoModal onClose={vi.fn()} />)
    expect(screen.getByText('Account types')).toBeInTheDocument()
    expect(screen.getByText('On budget = envelopes')).toBeInTheDocument()
    expect(screen.getByText('Off budget = net worth only')).toBeInTheDocument()
  })

  it('keeps the import notes out of the ordinary account context', () => {
    render(<AccountTypeInfoModal onClose={vi.fn()} />)
    expect(screen.queryByText('Import, close, or leave out')).not.toBeInTheDocument()
  })

  describe('in the import context', () => {
    it('adapts the title, since it now covers more than types', () => {
      render(<AccountTypeInfoModal context="import" onClose={vi.fn()} />)
      expect(screen.getByText('Account types & import choices')).toBeInTheDocument()
    })

    it('says what leaving an account out costs', () => {
      render(<AccountTypeInfoModal context="import" onClose={vi.fn()} />)
      expect(screen.getByText('Import, close, or leave out')).toBeInTheDocument()
      expect(screen.getByText(/net worth over time has a hole/)).toBeInTheDocument()
    })

    it('offers closing as the alternative that keeps the history', () => {
      render(<AccountTypeInfoModal context="import" onClose={vi.fn()} />)
      expect(
        screen.getByText(/Imported & closed — the safe choice for a dormant account/)
      ).toBeInTheDocument()
      expect(screen.getByText(/transfers to it still pair up/)).toBeInTheDocument()
    })

    it('names dropping an account as the cause of unmatched transfers', () => {
      // The connection the toast could never make on its own.
      render(<AccountTypeInfoModal context="import" onClose={vi.fn()} />)
      expect(screen.getByText(/nothing to pair with/)).toBeInTheDocument()
      expect(screen.getByText(/leaving accounts out is what causes it/)).toBeInTheDocument()
    })

    it('still lists the types', () => {
      render(<AccountTypeInfoModal context="import" onClose={vi.fn()} />)
      expect(screen.getByText('Off budget = net worth only')).toBeInTheDocument()
    })
  })

  describe('money in and money out', () => {
    it('renders the served lines for the shape a type defaults to', () => {
      render(<AccountTypeInfoModal types={[OTHER_ASSET]} budgetId="b1" onClose={vi.fn()} />)
      expect(screen.getByText(/Served buying line: counts as Spending/)).toBeInTheDocument()
      expect(screen.getByText(/Served selling line: counts as Income/)).toBeInTheDocument()
      expect(screen.getByText(/Ready to Assign goes up by/)).toBeInTheDocument()
      expect(vi.mocked(useMoneyRules)).toHaveBeenCalledWith('b1')
    })

    it('draws nothing for a type no served shape matches', () => {
      const saving = { ...OTHER_ASSET, key: 'brokerage', default_counts_as_savings: true }
      render(<AccountTypeInfoModal types={[saving]} budgetId="b1" onClose={vi.fn()} />)
      expect(screen.queryByText(/Served buying line/)).not.toBeInTheDocument()
    })

    it('does not ask for them while importing, before a budget exists', () => {
      render(<AccountTypeInfoModal context="import" budgetId="b1" onClose={vi.fn()} />)
      expect(vi.mocked(useMoneyRules)).toHaveBeenLastCalledWith(null)
    })
  })
})
