import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query)
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches
  )
}

/** Single source of truth for the app's mobile breakpoint (must match the CSS 768px). */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 768px)')
}

/**
 * True on devices with no hover — i.e. where focusing a field raises an
 * on-screen keyboard. Matches the `@media (hover: none)` blocks in the CSS,
 * so JS and styling agree on what "touch" means.
 */
export function useIsTouch(): boolean {
  return useMediaQuery('(hover: none)')
}
