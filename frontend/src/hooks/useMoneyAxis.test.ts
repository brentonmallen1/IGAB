/**
 * The money axis every chart spreads. Its tests used to assert a test-local
 * copy of the deleted tick formatter and re-check `compactMoney`, so nothing
 * reached the hook the charts actually call: its phone branch, its width or
 * its privacy mask could all break with the suite green.
 */
import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const phone = vi.hoisted(() => ({ current: false }))
vi.mock('./useMediaQuery', () => ({ useIsMobile: () => phone.current }))

import { useMoneyAxis } from './useMoneyAxis'
import { useAppStore } from '../stores/appStore'
import { MONEY_AXIS_WIDTH } from '../utils/moneyAxis'

afterEach(() => {
  phone.current = false
  useAppStore.setState({ privacyMode: false })
})

function axis() {
  return renderHook(() => useMoneyAxis()).result.current
}

describe('useMoneyAxis', () => {
  it('gives a desktop every cent in the wide gutter', () => {
    const { tickFormatter, width } = axis()
    expect(width).toBe(MONEY_AXIS_WIDTH.desktop)
    expect(tickFormatter(12345.67)).toBe('$12,345.67')
  })

  it('gives a phone a compact tick in the narrow gutter', () => {
    // The paydown chart drew "$12,345.67" in an 85px gutter on a phone while
    // the Asset page beside it read "$12k".
    phone.current = true
    const { tickFormatter, width } = axis()
    expect(width).toBe(MONEY_AXIS_WIDTH.phone)
    expect(tickFormatter(12345.67)).toBe('$12k')
    expect(tickFormatter(2_400_000)).toBe('$2.4M')
  })

  it('masks every tick in privacy mode, on a phone too', () => {
    useAppStore.setState({ privacyMode: true })
    expect(axis().tickFormatter(12345.67)).toBe('$••••')
    phone.current = true
    const masked = axis().tickFormatter(12345.67)
    expect(masked).toBe('$••••')
    expect(masked).not.toMatch(/\d/)
  })
})
