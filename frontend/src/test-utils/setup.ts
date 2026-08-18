import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
// Charts render zero-size under it; component tests assert surrounding UI.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver

// jsdom implements no media queries at all, so useMediaQuery/useIsMobile throws
// in any component that consults the breakpoint. Default to desktop; a test
// that needs the mobile branch mocks useMediaQuery directly, as the transaction
// editor suite does.
globalThis.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia

afterEach(() => {
  cleanup()
})
