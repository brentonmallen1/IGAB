import { useLocation, useNavigate } from 'react-router-dom'
import { overlayStackDepth } from '../utils/overlayStack'
import { parentRoute } from '../utils/routes'
import { useSwipeNavigation, type SwipeHandlers } from './useSwipeNavigation'

/**
 * A rightward swipe from the left screen edge goes back a level.
 *
 * An installed iOS PWA has no back gesture: Safari's edge swipe belongs to
 * the browser and the home-screen app does not get one. So a drill-in page —
 * an account register, a liability — could only be left through the bottom
 * nav. This supplies the gesture on the shell's content column. Overlays
 * own their own dismissal (history entry, drag, X), so while one is open the
 * gesture does nothing rather than navigating underneath it.
 */
export function useEdgeSwipeBack(): SwipeHandlers {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  return useSwipeNavigation({
    onEdgeBack: () => {
      if (overlayStackDepth() > 0) return
      const to = parentRoute(pathname)
      if (to !== pathname) navigate(to)
    },
  })
}
