import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '../../stores/appStore'
import {
  EMPTY_FUND_PICKER,
  FUND_COUNTING_LINE,
  FUND_PICKER,
} from '../../test-utils/emergencyFundFixtures'

const state = vi.hoisted(() => ({ picker: undefined as unknown }))

vi.mock('../../api/emergencyFund', () => ({
  useEmergencyFund: () => ({ data: state.picker }),
}))
vi.mock('./EmergencyFundPicker', () => ({
  EmergencyFundPicker: ({ from }: { from?: string }) => (
    <div role="dialog" aria-label="picker">
      from:{from ?? 'none'}
    </div>
  ),
}))

import { EmergencyFundCounting, EmergencyFundCountingView } from './EmergencyFundCounting'

beforeEach(() => {
  state.picker = FUND_PICKER
  useAppStore.setState({ privacyMode: false })
})

describe('EmergencyFundCountingView', () => {
  it('says what it counted, with a Change button', () => {
    const onChange = vi.fn()
    render(<EmergencyFundCountingView fund={FUND_PICKER.fund} onChange={onChange} />)
    expect(screen.getByText(FUND_COUNTING_LINE)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Change' }))
    expect(onChange).toHaveBeenCalled()
  })

  it('says it is not set up, and offers the choice', () => {
    render(<EmergencyFundCountingView fund={EMPTY_FUND_PICKER.fund} onChange={vi.fn()} />)
    expect(screen.getByText('Not set up —')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose what counts' })).toBeInTheDocument()
  })

  it('renders an example with no button when nothing can change', () => {
    render(<EmergencyFundCountingView fund={FUND_PICKER.fund} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('masks balances in privacy mode', () => {
    useAppStore.setState({ privacyMode: true })
    render(<EmergencyFundCountingView fund={FUND_PICKER.fund} />)
    expect(screen.queryByText(/\$2,400\.00/)).not.toBeInTheDocument()
  })
})

describe('EmergencyFundCounting', () => {
  it('renders nothing until the fund has loaded', () => {
    state.picker = undefined
    const { container } = render(<EmergencyFundCounting budgetId="b1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('opens the picker from its button, passing where it was opened from', () => {
    render(<EmergencyFundCounting budgetId="b1" from="guide" />)
    fireEvent.click(screen.getByRole('button', { name: 'Change' }))
    expect(screen.getByRole('dialog', { name: 'picker' })).toHaveTextContent('from:guide')
  })
})
