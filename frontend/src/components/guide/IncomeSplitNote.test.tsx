/**
 * The 50/30/20 roadmap node's live figure: the report's bar and what each gap
 * points to — a reading, never a grade, and only with personalization on.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { IncomeSplitReport } from '../../types'

const state = vi.hoisted(() => ({
  personal: true,
  data: undefined as IncomeSplitReport | undefined,
  asked: [] as unknown[][],
}))
vi.mock('../../api/guide', () => ({
  useGuideOverview: () => ({
    data: { preferences: { personalization: state.personal, checkup: true, wishlist: true } },
  }),
}))
vi.mock('../../api/reports', () => ({
  useIncomeSplitReport: (...args: unknown[]) => {
    state.asked.push(args)
    return { data: args[0] ? state.data : undefined }
  },
}))

import { IncomeSplitNote } from './IncomeSplitNote'
import { useAppStore } from '../../stores/appStore'

function split(over: Partial<IncomeSplitReport> = {}): IncomeSplitReport {
  return {
    start_date: '2026-07-01',
    end_date: '2026-09-30',
    months: 3,
    whole_months: true,
    running: false,
    clamped: false,
    tagged: true,
    spread_on: true,
    income: 7200,
    needs: { total: 4176, lines: [] },
    wants: { total: 1728, committed: [], chosen: [] },
    savings_debt: { total: 864, saved: [], debt: [] },
    uncategorized: { total: 144, count: 12 },
    left_over: 288,
    strict: { needs: 4101, savings_debt: 939 },
    ...over,
  }
}

function renderNote() {
  return render(
    <MemoryRouter>
      <IncomeSplitNote />
    </MemoryRouter>
  )
}

beforeEach(() => {
  state.personal = true
  state.data = split()
  state.asked = []
  useAppStore.setState({ currentBudgetId: 'b1' })
})

describe('IncomeSplitNote', () => {
  it('says what each gap points to', () => {
    renderNote()
    expect(screen.getByText('Needs 58% · 8 pts over')).toBeInTheDocument()
    expect(screen.getByText(/Needs move slowly/)).toBeInTheDocument()
    expect(screen.getByText('Wants 24% · 6 pts under')).toBeInTheDocument()
    expect(screen.getByText('Room you have already made.')).toBeInTheDocument()
    expect(screen.getByText('Saving 12% · 8 pts under')).toBeInTheDocument()
    expect(
      screen.getByText(/a starter emergency fund, then high-interest debt/)
    ).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Needs 58%/ })).toBeInTheDocument()
  })

  it('reads the last three complete months, whatever the report was left on', () => {
    renderNote()
    const [, start, end] = state.asked.at(-1)!
    expect(String(start).endsWith('-01')).toBe(true)
    expect(start).not.toBe(end)
  })

  it('reads nothing with personalization off', () => {
    state.personal = false
    const { container } = renderNote()
    expect(container).toBeEmptyDOMElement()
    expect(state.asked.at(-1)![0]).toBeNull()
  })

  it('asks for the Essential tag before there is a split to show', () => {
    state.data = split({ tagged: false })
    renderNote()
    expect(screen.getByText(/Tag the categories you couldn’t go without/)).toBeInTheDocument()
  })

  it('holds back the gaps while much of it is unfiled', () => {
    state.data = split({ uncategorized: { total: 2232, count: 86 }, left_over: -1800 })
    renderNote()
    expect(screen.getByText(/went out unfiled/)).toBeInTheDocument()
    expect(screen.queryByText(/pts over/)).toBeNull()
  })
})
