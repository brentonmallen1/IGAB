import { WishlistPanel } from '../../components/guide/wishlist/WishlistPanel'
// The wishlist grew up as a Guide tab and its controls still speak that
// stylesheet's vocabulary (guide-link-button, guide-viewswitch, the field
// rule) — imported here so this page stands alone without /guide ever having
// loaded its chunk.
import '../GuidePage/GuidePage.css'
import './WishlistPage.css'

/**
 * The wishlist, promoted out of the Guide: a working tool someone opens
 * weekly, not guidance read once. The panel is unchanged — this page only
 * gives it an address and the scroll container its sticky toolbar pins to.
 */
export function WishlistPage() {
  return (
    <main className="guide-content wishlist-page">
      <WishlistPanel />
    </main>
  )
}
