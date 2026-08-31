/**
 * What the Wishlist switch should send, decided apart from the page that sends it.
 *
 * Turning the Wishlist off archives its group, and an archived group takes
 * every envelope under it off the budget (`IN_ARCHIVED_GROUP`) — so anything
 * saved in a wish envelope would be unreachable. The server returns that money
 * to Ready to Assign, but only on an explicit `release_wishlist_money`: without
 * it the request is refused and the figure comes back as the error. That
 * refusal is what protects the money; this decides whether the user is asked
 * before it happens, and what the question says.
 *
 * Pure of React and of the network, the way `anchoredPosition` is pure of
 * `window`: the IO is injected, so every branch is a one-line test instead of a
 * mounted 36KB settings page. The page keeps the wiring — the real fetch, the
 * real dialog, the mutation.
 */

export interface WishlistRetireFacts {
  envelopes: string[]
  /** Canonical server decimal string. */
  available: string
  is_empty: boolean
}

/** What to PUT at the preferences endpoint, or null to do nothing at all. */
export interface WishlistToggleOutcome {
  wishlist: boolean
  release_wishlist_money?: boolean
}

export interface WishlistToggleDeps {
  /** Asked at the moment of the click; a cached figure could name money that
   *  is no longer there. */
  fetchPreview: () => Promise<WishlistRetireFacts>
  confirm: (message: { title: string; message: string; confirmLabel: string }) => Promise<boolean>
  /** The user's own money formatting, so the dialog reads like the rest of the app. */
  formatMoney: (amount: string) => string
  onPreviewFailed: () => void
}

export async function wishlistToggleOutcome(
  next: boolean,
  deps: WishlistToggleDeps
): Promise<WishlistToggleOutcome | null> {
  // Turning it ON moves no money and archives nothing, so it never asks.
  if (next) return { wishlist: true }

  let preview: WishlistRetireFacts
  try {
    preview = await deps.fetchPreview()
  } catch {
    // Never fall through to the mutation on a failed preview: the server would
    // refuse it anyway, but sending it would put a raw error in front of
    // someone who was told nothing about what was at stake.
    deps.onPreviewFailed()
    return null
  }

  if (preview.is_empty) {
    // Nothing to move, so nothing to ask about — and no consent flag, because
    // there is no money for it to consent to.
    return { wishlist: false }
  }

  const ok = await deps.confirm({
    title: 'Turn off the wishlist?',
    message:
      `Your wishlist holds ${deps.formatMoney(preview.available)} in ` +
      `${preview.envelopes.join(', ')}. Turning it off returns that to Ready to Assign ` +
      'and archives the envelopes — their history is kept, and turning the wishlist ' +
      'back on brings them back empty.',
    confirmLabel: 'Turn off and return the money',
  })
  if (!ok) return null
  return { wishlist: false, release_wishlist_money: true }
}
