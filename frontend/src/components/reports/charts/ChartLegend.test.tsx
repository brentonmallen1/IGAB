import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChartLegend } from './ChartLegend'

const series = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    name: `Group ${i}`,
    color: `var(--chart-${(i % 8) + 1})`,
    value: `$${i}`,
  }))

describe('ChartLegend', () => {
  it('lists every series — the chart draws them all', () => {
    render(<ChartLegend series={series(12)} active={null} onHover={() => {}} />)
    expect(screen.getAllByRole('button')).toHaveLength(12)
  })

  it('names the figure alongside, so the key is not only a list of names', () => {
    render(<ChartLegend series={series(2)} active={null} onHover={() => {}} />)
    expect(screen.getByRole('button', { name: 'Group 1, $1' })).toBeTruthy()
  })

  it('reports what the pointer is over', () => {
    const onHover = vi.fn()
    render(<ChartLegend series={series(3)} active={null} onHover={onHover} />)
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Group 1, $1' }))
    expect(onHover).toHaveBeenCalledWith('Group 1')
  })

  it('reports the same from the keyboard', () => {
    // The palette repeats past eight slots, so highlighting is how two
    // same-coloured bands are told apart — it cannot be pointer-only.
    const onHover = vi.fn()
    render(<ChartLegend series={series(3)} active={null} onHover={onHover} />)
    fireEvent.focus(screen.getByRole('button', { name: 'Group 2, $2' }))
    expect(onHover).toHaveBeenCalledWith('Group 2')
  })

  it('dims every entry except the active one', () => {
    render(<ChartLegend series={series(3)} active="Group 1" onHover={() => {}} />)
    const dimmed = screen
      .getAllByRole('button')
      .filter((b) => b.className.includes('is-dimmed'))
      .map((b) => b.textContent)
    expect(dimmed).toHaveLength(2)
    expect(dimmed.join()).not.toContain('Group 1')
  })

  it('dims nothing when nothing is active', () => {
    render(<ChartLegend series={series(3)} active={null} onHover={() => {}} />)
    expect(
      screen.getAllByRole('button').filter((b) => b.className.includes('is-dimmed'))
    ).toHaveLength(0)
  })
})
