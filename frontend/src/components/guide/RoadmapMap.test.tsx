import { describe, it, expect, beforeAll } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { RoadmapMap } from './RoadmapMap'
import { ROADMAP } from '../../content/roadmap'
import { buildFlow } from './flowLayout'

/** The layout maths is covered in flowLayout.test.ts. This checks the chart
 *  actually renders one box per node, draws a wire per edge, and that folding
 *  a step really removes its boxes — the things a unit test of pure geometry
 *  cannot see. */

beforeAll(() => {
  // jsdom has no pointer capture; the pan handlers call it on every drag.
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = () => {}
    Element.prototype.releasePointerCapture = () => {}
  }
})

function renderMap() {
  return render(
    <MemoryRouter>
      <RoadmapMap />
    </MemoryRouter>
  )
}

describe('RoadmapMap', () => {
  it('draws a box for every node in the roadmap', () => {
    const { container } = renderMap()
    const boxes = container.querySelectorAll('.flow-node')
    expect(boxes).toHaveLength(ROADMAP.flatMap((s) => s.nodes).length)
  })

  it('draws a wire for every edge', () => {
    const { container } = renderMap()
    expect(container.querySelectorAll('.flow__wire')).toHaveLength(buildFlow().edges.length)
  })

  it('labels the branch arrows', () => {
    const { container } = renderMap()
    const labels = [...container.querySelectorAll('.flow__wire-label')].map((n) => n.textContent)
    expect(labels).toContain('No')
    expect(labels).toContain('Yes')
    // Two answers sharing an outcome are merged onto one arrow.
    expect(labels).toContain('Yes / Not sure')
  })

  it('gives arrows a head so direction is readable', () => {
    const { container } = renderMap()
    expect(container.querySelector('marker#flow-arrow')).toBeTruthy()
    for (const w of container.querySelectorAll('.flow__wire')) {
      expect(w.getAttribute('marker-end')).toBe('url(#flow-arrow)')
    }
  })

  it('opens the full node when a box is clicked', async () => {
    const user = userEvent.setup()
    renderMap()
    await user.click(screen.getByRole('button', { name: /Build a budget/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Everything after this depends on/)).toBeInTheDocument()
  })

  it('folds a step down to a single box and back', async () => {
    const user = userEvent.setup()
    const { container } = renderMap()
    const total = ROADMAP.flatMap((s) => s.nodes).length
    const foundation = ROADMAP[0]

    await user.click(screen.getByRole('button', { name: `Collapse step ${foundation.step}` }))
    expect(container.querySelectorAll('.flow-node')).toHaveLength(total - foundation.nodes.length)
    expect(container.querySelectorAll('.flow-stage')).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: /click to expand|Expand this step/ }))
    expect(container.querySelectorAll('.flow-node')).toHaveLength(total)
    expect(container.querySelectorAll('.flow-stage')).toHaveLength(0)
  })

  it('exposes zoom controls and reports the level', async () => {
    const user = userEvent.setup()
    const { container } = renderMap()
    expect(screen.getByLabelText('Fit to width')).toBeInTheDocument()
    // Read the toolbar readout specifically — node titles contain "15%" too.
    const level = () => container.querySelector('.flow__zoom-level')!.textContent
    const before = level()
    await user.click(screen.getByLabelText('Zoom in'))
    expect(level()).not.toBe(before)
    await user.click(screen.getByLabelText('Zoom out'))
    expect(level()).toBe(before)
  })
})
