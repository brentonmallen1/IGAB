import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CatchOuts } from './CatchOuts'
import { CATCH_OUTS } from './money/catchOutList'
import { ASIDE_CATCH_OUTS } from './aside/asideCatchOuts'

describe('CatchOuts', () => {
  it('lists How money counts’ items, each with its try action', async () => {
    const run = vi.fn()
    render(
      <CatchOuts
        items={CATCH_OUTS}
        action={{ label: 'Try it', describe: (c) => `Try it: ${c.title}`, run }}
      />
    )
    expect(screen.getAllByRole('listitem')).toHaveLength(CATCH_OUTS.length)
    expect(screen.getAllByRole('button', { name: /^Try it:/ })).toHaveLength(CATCH_OUTS.length)
    await userEvent.click(screen.getByRole('button', { name: `Try it: ${CATCH_OUTS[2].title}` }))
    expect(run).toHaveBeenCalledWith(CATCH_OUTS[2])
  })

  it('lists Setting money aside’s items with no button', () => {
    render(<CatchOuts items={ASIDE_CATCH_OUTS} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(ASIDE_CATCH_OUTS.length)
    for (const item of ASIDE_CATCH_OUTS) {
      expect(screen.getByRole('heading', { name: item.title })).toBeInTheDocument()
    }
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('gives every item a distinct id', () => {
    for (const items of [CATCH_OUTS, ASIDE_CATCH_OUTS]) {
      expect(new Set(items.map((c) => c.id)).size).toBe(items.length)
    }
  })
})
