import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ViewportRuler } from './ViewportRuler'
import { RULER_LINES } from './viewportRulerLines'
import { useAppStore } from '../../stores/appStore'

describe('ViewportRuler', () => {
  beforeEach(() => {
    useAppStore.setState({ viewportRulerOn: false })
    window.history.replaceState(null, '', '/')
  })

  it('renders nothing until switched on', () => {
    render(<ViewportRuler />)
    expect(screen.queryByTestId('viewport-ruler')).toBeNull()
  })

  it('draws every line with its CSS expression when on', () => {
    useAppStore.setState({ viewportRulerOn: true })
    render(<ViewportRuler />)
    const ruler = screen.getByTestId('viewport-ruler')
    for (const line of RULER_LINES) {
      const el = ruler.querySelector<HTMLElement>(`[data-line="${line.id}"]`)
      expect(el, line.id).not.toBeNull()
      for (const [prop, value] of Object.entries(line.style)) {
        expect(el!.style.getPropertyValue(prop), `${line.id} ${prop}`).toBe(value)
      }
    }
  })

  it('switches itself on from ?vvdebug=1', () => {
    window.history.replaceState(null, '', '/budget?vvdebug=1')
    render(<ViewportRuler />)
    expect(useAppStore.getState().viewportRulerOn).toBe(true)
    expect(screen.getByTestId('viewport-ruler')).toBeInTheDocument()
  })

  it('shows what the shell height is built from, and never lets pointer events through', () => {
    // The three lines that decide the diagnosis, pinned by name so the
    // screenshot-reading instructions in the plan stay true.
    const ids = RULER_LINES.map((l) => l.id)
    expect(ids).toEqual(expect.arrayContaining(['layout-bottom', 'app-h', 'app-h-plus-safe-top']))
    const css = readFileSync(resolve(__dirname, 'ViewportRuler.css'), 'utf8')
    expect(css).toMatch(/\.viewport-ruler\s*{[^}]*pointer-events:\s*none/)
  })
})
