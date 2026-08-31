import { useEffect, useRef, useState } from 'react'

/**
 * Reports whether a `position: sticky` element is currently pinned to the top
 * of its scroll container.
 *
 * A zero-height sentinel is inserted in flow just above the element; the
 * element is pinned exactly when the sentinel has scrolled out of the
 * container. Pure class toggle — no geometry is read, so Surface.css owns
 * what "stuck" looks like.
 */
export function useStuck<T extends HTMLElement>(enabled: boolean) {
  const ref = useRef<T>(null)
  const [stuck, setStuck] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!enabled || !el || typeof IntersectionObserver === 'undefined') {
      setStuck(false)
      return
    }
    const sentinel = document.createElement('div')
    sentinel.className = 'surface__sentinel'
    sentinel.setAttribute('aria-hidden', 'true')
    el.parentElement?.insertBefore(sentinel, el)
    const observer = new IntersectionObserver(([entry]) => setStuck(!entry.isIntersecting), {
      root: scrollParent(el),
      threshold: 0,
    })
    observer.observe(sentinel)
    return () => {
      observer.disconnect()
      sentinel.remove()
    }
  }, [enabled])

  return { ref, stuck }
}

/** Nearest ancestor that scrolls vertically, or null for the viewport. */
function scrollParent(el: HTMLElement): Element | null {
  let node: HTMLElement | null = el.parentElement
  while (node) {
    const { overflowY } = getComputedStyle(node)
    if (overflowY === 'auto' || overflowY === 'scroll') return node
    node = node.parentElement
  }
  return null
}
