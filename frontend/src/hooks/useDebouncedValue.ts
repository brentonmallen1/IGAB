import { useEffect, useState } from 'react'

/**
 * The value as it stood `delay` ms ago, once it has stopped changing.
 *
 * For inputs that drive a request: the liability page's what-if field and
 * the Guide's calculators both type into something the server answers, and
 * neither should ask on every keystroke.
 */
export function useDebouncedValue<T>(value: T, delay = 400): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const handle = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(handle)
  }, [value, delay])
  return settled
}
