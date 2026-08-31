/**
 * The switch that used to bury money.
 *
 * Turning the Wishlist off archived its group with a column write, and an
 * archived group takes every envelope under it off the budget — so a wish
 * envelope's balance stayed deducted from Ready to Assign, drawn nowhere, and
 * reachable only by turning the switch back on. The settings copy said the
 * money "stays exactly where it is", which was true of the row and false of
 * everything the user could see.
 *
 * The server's refusal is what protects the money now: without an explicit
 * `release_wishlist_money` it will not archive a wishlist that holds any, and
 * hands the figure back as the error. These tests are the other half — that
 * the user is asked before that flag is ever sent, and never after saying no.
 */
import { describe, expect, it, vi } from 'vitest'
import { wishlistToggleOutcome, type WishlistRetireFacts } from './wishlistToggle'

const HOLDS_MONEY: WishlistRetireFacts = {
  envelopes: ['New Bike', 'Camera Lens'],
  available: '400.0000',
  is_empty: false,
}
const EMPTY: WishlistRetireFacts = { envelopes: [], available: '0.0000', is_empty: true }

/** Built with the mocks kept concrete, so a test can read what was asked. */
function deps(opts: { facts?: WishlistRetireFacts; offline?: boolean; confirmed?: boolean } = {}) {
  return {
    fetchPreview: vi.fn(async () => {
      if (opts.offline) throw new Error('offline')
      return opts.facts ?? EMPTY
    }),
    confirm: vi.fn(
      async (_req: { title: string; message: string; confirmLabel: string }) =>
        opts.confirmed ?? true
    ),
    formatMoney: (a: string) => `$${Number(a).toFixed(2)}`,
    onPreviewFailed: vi.fn(),
  }
}

describe('wishlistToggleOutcome', () => {
  it('turning it on asks nothing and moves nothing', async () => {
    const d = deps()
    expect(await wishlistToggleOutcome(true, d)).toEqual({ wishlist: true })
    // Not even a preview: there is no money question on the way in.
    expect(d.fetchPreview).not.toHaveBeenCalled()
    expect(d.confirm).not.toHaveBeenCalled()
  })

  it('an empty wishlist turns off with no dialog and no consent flag', async () => {
    // No money to consent to, so sending the flag anyway would be asking the
    // server for permission to move nothing.
    const d = deps({ facts: EMPTY })
    expect(await wishlistToggleOutcome(false, d)).toEqual({ wishlist: false })
    expect(d.confirm).not.toHaveBeenCalled()
  })

  it('asks before sending the flag that lets money move', async () => {
    const d = deps({ facts: HOLDS_MONEY })
    expect(await wishlistToggleOutcome(false, d)).toEqual({
      wishlist: false,
      release_wishlist_money: true,
    })
    expect(d.confirm).toHaveBeenCalledTimes(1)
  })

  it('states the amount and names the envelopes', async () => {
    // The figure is the server's, formatted with the user's own settings —
    // the dialog never adds it up itself.
    const d = deps({ facts: HOLDS_MONEY })
    await wishlistToggleOutcome(false, d)
    const asked = d.confirm.mock.calls[0][0]
    expect(asked.message).toContain('$400.00')
    expect(asked.message).toContain('New Bike')
    expect(asked.message).toContain('Camera Lens')
    // Says where the money goes, not just that something happens.
    expect(asked.message).toMatch(/Ready to Assign/)
    // And that the envelopes come back empty, so that is not a second surprise.
    expect(asked.message).toMatch(/back empty/)
  })

  it('sends nothing at all when the user declines', async () => {
    // The failure that matters: a cancel that still flipped the switch would
    // move the money the dialog just warned about.
    const d = deps({ facts: HOLDS_MONEY, confirmed: false })
    expect(await wishlistToggleOutcome(false, d)).toBeNull()
  })

  it('sends nothing when the preview cannot be fetched, and says so', async () => {
    // Falling through would put a raw server refusal in front of someone who
    // was never told what was at stake.
    const d = deps({ offline: true })
    expect(await wishlistToggleOutcome(false, d)).toBeNull()
    expect(d.onPreviewFailed).toHaveBeenCalledTimes(1)
    expect(d.confirm).not.toHaveBeenCalled()
  })

  it('never sends the consent flag without having asked', async () => {
    // The invariant, swept over every path rather than trusted per branch.
    for (const [next, facts] of [
      [true, EMPTY],
      [false, EMPTY],
      [false, HOLDS_MONEY],
    ] as const) {
      const d = deps({ facts })
      const out = await wishlistToggleOutcome(next, d)
      if (out?.release_wishlist_money) expect(d.confirm).toHaveBeenCalled()
    }
  })
})
