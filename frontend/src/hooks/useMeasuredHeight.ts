import { useCallback, useLayoutEffect, useRef, useState } from 'react'

/**
 * The live pixel height of an element, for the one thing CSS cannot do:
 * offset a second sticky element by the height of the first.
 *
 * The budget grid stacks two sticky rows — the filter bar and the column
 * header — and the bar wraps to two lines on a narrow window, so its height
 * is not a constant anyone can type into a stylesheet. A guessed offset shows
 * a sliver of scrolling rows between them at one width and clips the header
 * at another.
 *
 * Returns 0 until the first measurement, which is the honest starting value:
 * an unmeasured bar contributes no offset, so the header sits where it did
 * before this hook existed.
 */
export function useMeasuredHeight<T extends HTMLElement>(): [(node: T | null) => void, number] {
  const [height, setHeight] = useState(0)
  const observerRef = useRef<ResizeObserver | null>(null)

  // A callback ref rather than an effect over a ref object: the node can be
  // swapped or unmounted (the bar is conditional on having a budget), and a
  // callback ref is told about that where an effect on `ref.current` is not.
  const ref = useCallback((node: T | null) => {
    observerRef.current?.disconnect()
    observerRef.current = null
    if (!node) {
      setHeight(0)
      return
    }
    setHeight(node.getBoundingClientRect().height)
    // Absent in jsdom and in older Safari; the measurement above still ran,
    // so the layout is correct at mount and merely stops tracking resizes.
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      setHeight(entry.target.getBoundingClientRect().height)
    })
    observer.observe(node)
    observerRef.current = observer
  }, [])

  useLayoutEffect(() => () => observerRef.current?.disconnect(), [])

  return [ref, height]
}
