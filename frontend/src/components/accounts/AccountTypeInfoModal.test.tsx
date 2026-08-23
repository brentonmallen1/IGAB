/**
 * The modal is the single home for type explanations, and — in the import
 * context — for what leaving an account out costs.
 *
 * That second part exists because nothing connected the choice to its
 * consequence: dropping an account is what produces the "1,117 transfers
 * couldn't be matched" warning, and that warning arrived as a toast long after
 * the decision was made, with no way back to it.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AccountTypeInfoModal } from './AccountTypeInfoModal'

describe('AccountTypeInfoModal', () => {
  it('explains the built-in types when no registry is passed', () => {
    render(<AccountTypeInfoModal onClose={vi.fn()} />)
    expect(screen.getByText('Account types')).toBeInTheDocument()
    expect(screen.getByText('On budget = envelopes')).toBeInTheDocument()
    expect(screen.getByText('Off budget = net worth only')).toBeInTheDocument()
  })

  it('keeps the import notes out of the ordinary account context', () => {
    render(<AccountTypeInfoModal onClose={vi.fn()} />)
    expect(screen.queryByText('Leaving an account out')).not.toBeInTheDocument()
  })

  describe('in the import context', () => {
    it('adapts the title, since it now covers more than types', () => {
      render(<AccountTypeInfoModal context="import" onClose={vi.fn()} />)
      expect(screen.getByText('Account types & import choices')).toBeInTheDocument()
    })

    it('says what leaving an account out costs', () => {
      render(<AccountTypeInfoModal context="import" onClose={vi.fn()} />)
      expect(screen.getByText('Leaving an account out')).toBeInTheDocument()
      expect(screen.getByText(/net worth over time has a hole/)).toBeInTheDocument()
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
})
