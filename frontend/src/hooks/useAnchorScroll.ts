import { useEffect, useRef } from 'react'

/**
 * Scroll to the element a URL hash names, once it exists.
 *
 * A Guide link like `/guide?tab=aside#emergency-fund` arrives before the tab
 * it names has rendered — the page switches tabs in an effect, and then
 * clears the query (which drops the hash). So the id is remembered when the
 * hash arrives and looked for after every render until the element is there;
 * it is scrolled to once, then forgotten, so later renders never yank the
 * reader back.
 */
export function useAnchorScroll(hash: string) {
  const pending = useRef<string | null>(null)

  useEffect(() => {
    const id = hash.replace(/^#/, '')
    if (id) pending.current = id
  }, [hash])

  useEffect(() => {
    const id = pending.current
    if (!id) return
    const target = document.getElementById(id)
    if (!target) return
    pending.current = null
    target.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  })
}
