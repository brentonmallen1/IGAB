/**
 * The treemap's tile renderer, handed nodes the way recharts hands them.
 * recharts lays the tree out at zero size under jsdom, so the renderer is
 * called directly with the geometry a real layout gives it.
 */
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { TreemapTile } from './WhereItWentTreemap'

const inSvg = (node: ReactNode) => render(<svg>{node}</svg>)

describe('TreemapTile', () => {
  it('draws nothing for the root, which used to print "$0.00" mid-chart', () => {
    const { container } = inSvg(<TreemapTile depth={0} x={0} y={0} width={800} height={440} />)
    expect(container.querySelector('svg')?.childElementCount).toBe(0)
    expect(container.textContent).not.toContain('$0.00')
  })

  it('draws a tile with its name and amount', () => {
    const { container } = inSvg(
      <TreemapTile depth={1} name="Groceries" size={420} x={0} y={0} width={200} height={120} />
    )
    expect(container.textContent).toContain('Groceries')
    expect(container.textContent).toContain('$420.00')
  })
})
