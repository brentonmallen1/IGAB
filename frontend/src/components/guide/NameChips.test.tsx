import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NameChips } from './NameChips'

const TWELVE = Array.from({ length: 12 }, (_, i) => `Card ${i + 1}`)

describe('NameChips', () => {
  it('folds the tail behind "+N more" and unfolds it', async () => {
    render(<NameChips names={TWELVE} limit={6} label="debts" />)
    expect(screen.getAllByRole('listitem')).toHaveLength(7) // six chips + the toggle
    expect(screen.getByText('Card 6')).toBeInTheDocument()
    expect(screen.queryByText('Card 7')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '+6 more' }))
    expect(screen.getByText('Card 12')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'show fewer' }))
    expect(screen.queryByText('Card 12')).not.toBeInTheDocument()
  })

  it('a short list has no toggle', () => {
    render(<NameChips names={['Visa', 'Store card']} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders nothing for no names', () => {
    const { container } = render(<NameChips names={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
