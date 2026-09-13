import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { GLOSSARY } from '../../content/glossary'
import { useGuideStore } from '../../stores/guideStore'
import { GlossaryPanel } from './GlossaryPanel'

beforeEach(() => {
  useGuideStore.setState({ openGlossaryTerm: null })
})

describe('a glossary entry with a Guide tab', () => {
  it('links the savings rate to How money counts', async () => {
    render(
      <MemoryRouter>
        <GlossaryPanel />
      </MemoryRouter>
    )
    await userEvent.click(screen.getByRole('button', { name: /^Savings rate/ }))
    expect(screen.getByRole('link', { name: /See how money counts/ })).toHaveAttribute(
      'href',
      '/guide?tab=money'
    )
  })

  it('draws no link on an entry without one', async () => {
    render(
      <MemoryRouter>
        <GlossaryPanel />
      </MemoryRouter>
    )
    const plain = GLOSSARY.find((e) => !e.guideTab)!
    await userEvent.click(screen.getByRole('button', { name: new RegExp(`^${plain.term}`) }))
    expect(screen.queryByRole('link', { name: /See / })).not.toBeInTheDocument()
  })
})
