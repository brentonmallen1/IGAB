import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { useAnchorScroll } from './useAnchorScroll'

function Page({ hash, showTarget }: { hash: string; showTarget: boolean }) {
  useAnchorScroll(hash)
  return showTarget ? <section id="emergency-fund">fund</section> : <p>another tab</p>
}

function spyScroll() {
  const spy = vi.fn()
  Element.prototype.scrollIntoView = spy
  return spy
}

describe('useAnchorScroll', () => {
  it('scrolls to the named section once it renders, then forgets it', () => {
    const spy = spyScroll()
    const { rerender } = render(<Page hash="#emergency-fund" showTarget={false} />)
    expect(spy).not.toHaveBeenCalled()
    // The tab switches, and the query (with its hash) is cleared.
    rerender(<Page hash="" showTarget />)
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy.mock.contexts[0]).toHaveProperty('id', 'emergency-fund')
    rerender(<Page hash="" showTarget />)
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('does nothing without a hash', () => {
    const spy = spyScroll()
    render(<Page hash="" showTarget />)
    expect(spy).not.toHaveBeenCalled()
  })
})
