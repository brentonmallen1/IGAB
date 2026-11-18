import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { FailureDetails } from './FailureDetails'

const failure = {
  headline: 'Couldn’t reach Ollama.',
  nextStep: 'Check that it’s running and that its address is right.',
  technical: 'ConnectError: All connection attempts failed',
  settings: 'System → AI',
}

describe('FailureDetails on a Scans row', () => {
  it('shows only the headline until Details is opened', async () => {
    render(
      <MemoryRouter>
        <FailureDetails failure={failure} variant="row" />
      </MemoryRouter>
    )
    expect(screen.getByText(failure.headline)).toBeInTheDocument()
    expect(screen.queryByText(/Check that it’s running/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByText(/Check that it’s running/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open System → AI' })).toBeInTheDocument()
    expect(screen.getByText(failure.technical)).toBeInTheDocument()
  })

  it('has no Details when there is nothing behind it', () => {
    render(
      <MemoryRouter>
        <FailureDetails
          failure={{ headline: 'Old error', nextStep: null, technical: null, settings: null }}
          variant="row"
        />
      </MemoryRouter>
    )
    expect(screen.queryByRole('button', { name: 'Details' })).not.toBeInTheDocument()
  })
})
