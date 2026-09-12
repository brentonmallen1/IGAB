import { useEffect, useState } from 'react'
import { useFormatters } from '../../../hooks/useFormatters'
import { COUNT_UP_MS, countUpValue } from '../../../utils/countUp'
import { prefersReducedMotion } from '../../../utils/motion'
import './CountUpMoney.css'

interface Props {
  /** Where the count starts — a figure the viewer has already seen. */
  from: number
  /** Where it stops. Printed exactly; the count only decides the frames between. */
  to: number
  className?: string
}

/**
 * A money figure that counts from one served value to another.
 *
 * The frames come from `countUpValue` (utils/countUp), which is the part with
 * the rules; this only drives it with requestAnimationFrame. It lands on `to`
 * at once when the viewer asked for less motion, and in privacy mode, where
 * every frame would print the same mask — animating hidden digits is motion
 * that says nothing.
 *
 * Screen readers get the final figure once: the counting digits are hidden
 * from them, or a live toast would announce every frame.
 */
export function CountUpMoney({ from, to, className }: Props) {
  const { formatMoney, privacyMode } = useFormatters()
  const instant = privacyMode || prefersReducedMotion()
  // Keyed to the figures it counts between: a newer toast reusing this
  // component starts its own count from zero instead of inheriting the old
  // one's finished clock and flashing its end figure first.
  const [clock, setClock] = useState({ from, to, elapsed: 0 })
  const elapsed = clock.from === from && clock.to === to ? clock.elapsed : 0

  useEffect(() => {
    if (instant) return
    const start = performance.now()
    let frame = 0
    const tick = () => {
      const now = performance.now() - start
      setClock({ from, to, elapsed: now })
      if (now < COUNT_UP_MS) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [from, to, instant])

  const shown = instant ? to : countUpValue(from, to, elapsed)
  return (
    <span className={['count-up-money', className].filter(Boolean).join(' ')}>
      <span aria-hidden="true">{formatMoney(shown)}</span>
      <span className="sr-only">{formatMoney(to)}</span>
    </span>
  )
}
