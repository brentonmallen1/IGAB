import { useEffect } from 'react'
import { keepsCategorySelection } from '../../utils/keepsSelection'

/** Clears the category selection on a pointer press outside what acts on it —
 *  see `keepsCategorySelection`. Listens only while something is selected. */
export function useDeselectOnOutsidePointer(active: boolean, clear: () => void) {
  useEffect(() => {
    if (!active) return
    const onPointerDown = (e: PointerEvent) => {
      if (!keepsCategorySelection(e.target, document.getElementById('root'))) clear()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [active, clear])
}
