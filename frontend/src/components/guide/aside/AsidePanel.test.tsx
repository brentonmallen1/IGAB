/**
 * Setting money aside renders what is served and computes nothing itself.
 * The served month and spread figures below are deliberately not the real
 * ones, so a passing assertion proves the component drew the response.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { useAppStore } from '../../../stores/appStore'
import { useMoneyMonth, type MonthMoveRequest } from '../../../api/moneyRules'
import { useSpreadExample } from '../../../api/guide'
import { ZERO_FIGURES, explanation } from '../../../test-utils/moneyRulesFixtures'
import { ASIDE_ANCHORS, asideHref } from '../../../utils/guideLinks'
import {
  meansTrend,
  meansTrendCountPhrase,
  meansTrendSub,
  meansTrendValue,
} from '../../reports/livingMeans'
import { AsidePanel } from './AsidePanel'
import { GENERAL_SAVINGS_REQUESTS } from './asideExampleMoves'
import { MEANS_EXAMPLE_MONTHS } from './meansExampleMonths'

vi.mock('../../../api/moneyRules', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/moneyRules')>()),
  useMoneyMonth: vi.fn(),
}))

vi.mock('../../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/guide')>()),
  useSpreadExample: vi.fn(),
}))

// recharts measures its container; jsdom has none.
vi.mock('../../reports/MeansTrendChart', () => ({
  MeansTrendChart: ({ label }: { label?: string }) => <div role="img" aria-label={label} />,
}))

/** A served month: per-row saved figures and envelope terms, and a total. */
function served(saved: number[], total: number, envelope: number[]) {
  return {
    data: {
      rows: GENERAL_SAVINGS_REQUESTS.sent_out.map((m, i) => ({
        label: m.label,
        explanation: explanation({
          budget_terms: [{ term: 'envelope', delta: envelope[i] }],
          figures: { ...ZERO_FIGURES, savings: saved[i] },
        }),
      })),
      class_totals: {},
      held: 0,
      figures: { ...ZERO_FIGURES, savings: total },
    },
    isError: false,
  } as unknown as ReturnType<typeof useMoneyMonth>
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <AsidePanel />
    </MemoryRouter>
  )
}

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  vi.mocked(useMoneyMonth).mockImplementation((_budget, moves) =>
    (moves as MonthMoveRequest[])[0].category === 'savings_kept'
      ? served([501, -121, 0], 381, [501, -121, -301])
      : served([0, 121, 301], 421, [501, -121, -301])
  )
  vi.mocked(useSpreadExample).mockReturnValue({
    data: {
      as_paid_after_bill: 2801,
      as_paid_otherwise: 2001,
      spread: 2201,
      bill_monthly_share: 201,
      goal_months: 3,
      goal_as_paid_after_bill: 8401,
      goal_as_paid_otherwise: 6001,
      goal_spread: 6601,
    },
    isError: false,
  } as unknown as ReturnType<typeof useSpreadExample>)
})

describe('Setting money aside', () => {
  it('renders every section under its anchor', () => {
    const { container } = renderPanel()
    expect(
      screen.getByRole('heading', { name: 'Setting money aside', level: 2 })
    ).toBeInTheDocument()
    for (const anchor of ASIDE_ANCHORS) {
      const section = container.querySelector(`#${anchor}`)
      expect(section, anchor).not.toBeNull()
      expect(within(section as HTMLElement).getAllByRole('heading')[0]).toBeVisible()
    }
    expect(
      screen.getByRole('heading', { name: 'Things that catch people out' })
    ).toBeInTheDocument()
  })

  it('asks for the sent-out month first and shows its served rows and total', () => {
    renderPanel()
    expect(vi.mocked(useMoneyMonth)).toHaveBeenCalledWith('b1', GENERAL_SAVINGS_REQUESTS.sent_out)
    const table = screen.getByRole('table', {
      name: /General Savings, counted as saved when it leaves the budget/,
    })
    const repair = within(table)
      .getByRole('rowheader', { name: /Car repair/ })
      .closest('tr')!
    expect(within(repair).getByText('+$121.00')).toBeInTheDocument()
    expect(within(table).getByText('+$421.00')).toBeInTheDocument()
    expect(screen.getByText('Either way, $79.00 is still in the envelope.')).toBeInTheDocument()
  })

  it('switches to in the budget and shows that served month', async () => {
    renderPanel()
    await userEvent.click(screen.getByRole('radio', { name: 'In budget' }))
    expect(vi.mocked(useMoneyMonth)).toHaveBeenLastCalledWith(
      'b1',
      GENERAL_SAVINGS_REQUESTS.kept_here
    )
    const table = screen.getByRole('table', {
      name: /General Savings, counted as saved while it’s in the budget/,
    })
    const assign = within(table)
      .getByRole('rowheader', { name: /Assigned/ })
      .closest('tr')!
    expect(within(assign).getByText('+$501.00')).toBeInTheDocument()
    expect(within(table).getByText('−$121.00')).toBeInTheDocument()
    expect(within(table).getByText('+$381.00')).toBeInTheDocument()
  })

  it('the two month requests differ only in the category kind', () => {
    const strip = (moves: MonthMoveRequest[]) => moves.map(({ category: _, ...rest }) => rest)
    expect(strip(GENERAL_SAVINGS_REQUESTS.kept_here)).toEqual(
      strip(GENERAL_SAVINGS_REQUESTS.sent_out)
    )
    expect(GENERAL_SAVINGS_REQUESTS.sent_out.map((m) => m.category)).toEqual(
      Array(3).fill('savings_sent')
    )
    expect(GENERAL_SAVINGS_REQUESTS.kept_here.map((m) => m.category)).toEqual(
      Array(3).fill('savings_kept')
    )
  })

  it('says when the month could not be loaded', () => {
    vi.mocked(useMoneyMonth).mockReturnValue({ data: undefined, isError: true } as never)
    renderPanel()
    expect(screen.getByText('The example could not be loaded.')).toBeInTheDocument()
  })

  it('shows the served spread figures', () => {
    renderPanel()
    const cards = screen.getByLabelText('Spread example')
    expect(within(cards).getByText('$2,801.00 / mo')).toBeInTheDocument()
    expect(within(cards).getByText('$2,201.00 / mo')).toBeInTheDocument()
    expect(within(cards).getByText('$201.00')).toBeInTheDocument()
    expect(within(cards).getByText('$6,601.00')).toBeInTheDocument()
    expect(within(cards).getByText('$8,401.00')).toBeInTheDocument()
    expect(within(cards).getByText('$6,001.00')).toBeInTheDocument()
  })

  it('reads the Means example through meansTrend', () => {
    renderPanel()
    const trend = meansTrend(MEANS_EXAMPLE_MONTHS)
    const section = document.getElementById('means-trend')!
    expect(within(section).getByText(meansTrendValue(trend.recent))).toBeInTheDocument()
    expect(
      within(section).getByText(`${meansTrendSub(trend)} · ${meansTrendCountPhrase(trend)}`)
    ).toBeInTheDocument()
    expect(
      within(section).getByRole('img', { name: meansTrendCountPhrase(trend) })
    ).toBeInTheDocument()
    // Checked on paper: Oct–Dec keep 2,160 of 18,000; Jul–Sep ran 750 short.
    expect(meansTrendValue(trend.recent)).toBe('Keeping 12%')
    expect(trend.belowCount).toBe(8)
  })

  it('draws the example Counting line with no Change button', () => {
    renderPanel()
    const section = document.getElementById('emergency-fund')!
    expect(
      within(section).getByText(
        'Emergency Fund envelope $2,400.00 · Harborstone Reserve $6,000.00 · kept elsewhere $1,000.00'
      )
    ).toBeInTheDocument()
    expect(within(section).queryByRole('button', { name: 'Change' })).not.toBeInTheDocument()
  })

  it('links out to where your own figures are', () => {
    renderPanel()
    const href = (name: RegExp | string) => screen.getByRole('link', { name }).getAttribute('href')
    expect(href('Settings → Tags')).toBe('/settings/tags')
    expect(href('Emergency Fund')).toBe('/reports?tab=emergency-fund')
    expect(href('sizer')).toBe('/guide?tab=tools&tool=emergency-fund')
    expect(href('Open the Essentials report')).toBe('/reports?tab=essentials')
    expect(href('Open the Overview')).toBe('/reports?tab=overview')
    expect(href('Open the Savings report')).toBe('/reports?tab=savings')
    expect(href('How money counts')).toBe('/guide?tab=money')
    expect(asideHref('savings-modes')).toBe('/guide?tab=aside#savings-modes')
  })

  it('lists its catch-outs with no try action', () => {
    renderPanel()
    expect(
      screen.getByText(
        /An envelope that counts as saved when it leaves the budget counts a repair as saved/
      )
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Try it/ })).not.toBeInTheDocument()
  })
})
