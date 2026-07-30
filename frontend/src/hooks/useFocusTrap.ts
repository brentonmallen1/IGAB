import { useEffect, useRef } from 'react'
import { createFocusTrap } from 'focus-trap'

/**
 * Traps keyboard focus inside the referenced element while it is mounted
 * (WCAG 2.4.3). Focus returns to the previously focused element on unmount.
 *
 * Attach the returned ref to the dialog container and give it tabIndex={-1}
 * so it can receive fallback focus when nothing inside is tabbable yet.
 * When `onEscape` is provided, pressing Escape inside the dialog calls it.
 */
export function useFocusTrap<T extends HTMLElement>(onEscape?: () => void) {
  const ref = useRef<T>(null)
  const escapeRef = useRef(onEscape)
  useEffect(() => {
    escapeRef.current = onEscape
  })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const trap = createFocusTrap(el, {
      escapeDeactivates: false,
      allowOutsideClick: true,
      fallbackFocus: el,
      returnFocusOnDeactivate: true,
    })
    trap.activate()
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && escapeRef.current) {
        e.stopPropagation()
        escapeRef.current()
      }
    }
    el.addEventListener('keydown', onKeyDown)
    return () => {
      el.removeEventListener('keydown', onKeyDown)
      trap.deactivate()
    }
  }, [])
  return ref
}
