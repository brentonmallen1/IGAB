import { useEffect, useRef } from 'react'
import { createFocusTrap, type FocusTargetOrFalse } from 'focus-trap'

export interface FocusTrapOptions {
  /**
   * What receives focus on activation. Pass `false` when the dialog's content
   * already manages its own focus (e.g. an `autoFocus` amount field) —
   * otherwise focus-trap moves focus to the container and the keyboard the
   * user was about to type into never opens.
   */
  initialFocus?: FocusTargetOrFalse
}

/**
 * Traps keyboard focus inside the referenced element while it is mounted
 * (WCAG 2.4.3). Focus returns to the previously focused element on unmount.
 *
 * Attach the returned ref to the dialog container and give it tabIndex={-1}
 * so it can receive fallback focus when nothing inside is tabbable yet.
 * When `onEscape` is provided, pressing Escape inside the dialog calls it.
 *
 * The effect runs once on mount and reads `ref.current` immediately, so the
 * element must exist by then: a component that stays mounted and renders
 * `null` while closed will never activate the trap. Mount the trapped panel
 * conditionally instead.
 */
export function useFocusTrap<T extends HTMLElement>(
  onEscape?: () => void,
  options?: FocusTrapOptions
) {
  const ref = useRef<T>(null)
  const escapeRef = useRef(onEscape)
  useEffect(() => {
    escapeRef.current = onEscape
  })

  // Read once: the trap is created on mount and options can't change after.
  const initialFocusRef = useRef(options?.initialFocus)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const trap = createFocusTrap(el, {
      escapeDeactivates: false,
      allowOutsideClick: true,
      fallbackFocus: el,
      returnFocusOnDeactivate: true,
      ...(initialFocusRef.current !== undefined
        ? { initialFocus: initialFocusRef.current }
        : {}),
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
