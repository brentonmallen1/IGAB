import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StageMark } from './StageMark'
import { useSetGuideStep } from '../../api/guide'

vi.mock('../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/guide')>()),
  useSetGuideStep: vi.fn(),
}))

const mutate = vi.fn()

beforeEach(() => {
  mutate.mockReset()
  vi.mocked(useSetGuideStep).mockReturnValue({
    mutate,
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useSetGuideStep>)
})

describe('StageMark', () => {
  it('marks a stage done', async () => {
    render(<StageMark budgetId="b1" stageId="foundation" />)
    await userEvent.click(screen.getByRole('button', { name: 'Mark done' }))
    expect(mutate).toHaveBeenCalledWith({ stageId: 'foundation', state: 'done' })
  })

  it('skips a stage', async () => {
    render(<StageMark budgetId="b1" stageId="employer-match" />)
    await userEvent.click(screen.getByRole('button', { name: 'Skip' }))
    expect(mutate).toHaveBeenCalledWith({ stageId: 'employer-match', state: 'skipped' })
  })

  it('shows the mark and undoes it with a null state', async () => {
    render(<StageMark budgetId="b1" stageId="foundation" mark="done" />)
    expect(screen.getByText('you marked this done')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark done' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(mutate).toHaveBeenCalledWith({ stageId: 'foundation', state: null })
  })

  it('a collapsed row shows an existing mark but offers nothing', () => {
    const { container, rerender } = render(
      <StageMark budgetId="b1" stageId="foundation" showControls={false} />
    )
    expect(container).toBeEmptyDOMElement()
    rerender(<StageMark budgetId="b1" stageId="foundation" mark="skipped" showControls={false} />)
    expect(screen.getByText('you skipped this')).toBeInTheDocument()
  })
})
