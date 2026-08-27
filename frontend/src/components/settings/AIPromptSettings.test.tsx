import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AIPromptSettings } from './AIPromptSettings'
import { useResetSetting, useSettings, useUpdateSetting } from '../../api/settings'

vi.mock('../../api/settings', () => ({
  useSettings: vi.fn(),
  useUpdateSetting: vi.fn(),
  useResetSetting: vi.fn(),
}))

beforeEach(() => {
  vi.mocked(useSettings).mockReturnValue({
    data: [
      { key: 'ai_prompt_suggest_regex', value: 'names: {names}', is_overridden: false, placeholders: ['{names}'] },
      { key: 'ai_prompt_receipt_gate', value: 'gate', is_overridden: true, placeholders: [] },
    ],
  } as never)
  vi.mocked(useUpdateSetting).mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never)
  vi.mocked(useResetSetting).mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never)
})

describe('AIPromptSettings', () => {
  it('says where every prompt runs without opening the card', () => {
    render(<AIPromptSettings />)
    expect(screen.getByText(/beside a payee’s match pattern/)).toBeInTheDocument()
    expect(screen.getByText(/AI Suggest button beside the category field/)).toBeInTheDocument()
    expect(screen.getByText(/natural-language entry in Quick Add/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { expanded: false })).toHaveLength(5)
  })

  it('shows the served placeholders once a card is open', async () => {
    render(<AIPromptSettings />)
    await userEvent.click(screen.getByRole('button', { name: /Match pattern suggestion/ }))
    expect(screen.getByText('{names}')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Receipt gate/ }))
    expect(screen.getByText('none')).toBeInTheDocument()
    expect(screen.getByText('edited')).toBeInTheDocument()
  })
})
