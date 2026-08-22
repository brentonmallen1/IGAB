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

// jsdom here ships without localStorage, so every zustand `persist` store
// throws the first time a test calls a setter — the stores stay readable but
// are untestable the moment they change. Install a real one for the whole
// suite rather than per file; a browser always has it.
class MemoryStorage implements Storage {
  private store = new Map<string, string>()
  get length() { return this.store.size }
  key(i: number) { return [...this.store.keys()][i] ?? null }
  getItem(k: string) { return this.store.get(k) ?? null }
  setItem(k: string, v: string) { this.store.set(k, String(v)) }
  removeItem(k: string) { this.store.delete(k) }
  clear() { this.store.clear() }
}

// The property is declared but undefined here, so `in` is not the test.
if (globalThis.localStorage === undefined) {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: new MemoryStorage(),
  })
}

afterEach(() => {
  cleanup()
  localStorage.clear()
})
