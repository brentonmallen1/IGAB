import { useEffect } from 'react'
import { pressKeepsSelection } from '../utils/keepsSelection'

/** Clears a selection on a pointer press outside what acts on it — see
 *  `pressKeepsSelection`. Listens only while something is selected. Used by
 *  the budget (categories) and the register (transactions). */
export function useDeselectOnOutsidePointer(active: boolean, clear: () => void) {
  useEffect(() => {
    if (!active) return
    const onPointerDown = (e: PointerEvent) => {
      if (!pressKeepsSelection(e.target, document.getElementById('root'))) clear()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [active, clear])
}
