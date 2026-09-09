import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('../../../api/aiChat', () => ({
  useConversations: () => ({
    isLoading: false,
    data: [
      {
        id: 'c1',
        title: 'Why is Groceries overspent?',
        created_at: '2026-09-08T10:00:00Z',
        updated_at: '2026-09-08T10:00:00Z',
        message_count: 2,
      },
    ],
  }),
  useConversation: (_budgetId: string | null, conversationId: string | null) => ({
    isLoading: false,
    data:
      conversationId === 'c1'
        ? {
            id: 'c1',
            title: 'Why is Groceries overspent?',
            created_at: '2026-09-08T10:00:00Z',
            updated_at: '2026-09-08T10:00:00Z',
            message_count: 2,
            messages: [
              {
                id: 'm1',
                role: 'user',
                content: 'Why is Groceries overspent?',
                thinking: null,
                tool_calls: null,
                grounding: null,
                created_at: '2026-09-08T10:00:00Z',
                ai_call_id: null,
              },
              {
                id: 'm2',
                role: 'assistant',
                content: 'Groceries is over by `$42.00` in September.',
                thinking: null,
                tool_calls: [
                  {
                    name: 'get_budget_month',
                    arguments: { month: '2026-09' },
                    resolved_arguments: { month: '2026-09-01' },
                    delegates_to: 'BudgetService.get_month',
                    row_count: 12,
                    truncated: false,
                    duration_ms: 20,
                    error: null,
                  },
                ],
                grounding: { figures: 1, grounded: 1, derived: 0, unsupported: [], lookups: 1 },
                created_at: '2026-09-08T10:00:05Z',
                ai_call_id: null,
              },
            ],
          }
        : undefined,
  }),
  useDeleteConversation: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('../../../hooks/useFormatters', () => ({
  useFormatters: () => ({ formatDate: (d: string) => d }),
}))

import { ChatsTab } from './ChatsTab'

describe('ChatsTab', () => {
  it('opens a row to the transcript, with what the answer looked up', () => {
    render(<ChatsTab budgetId="b1" />)
    expect(screen.queryByText(/over by/)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /^Why is Groceries/ }))

    expect(screen.getByText('$42.00')).toBeInTheDocument()
    expect(screen.getByText(/Checked your budget 1 time/)).toBeInTheDocument()
  })

  it('keeps a way to continue the conversation in the panel', () => {
    render(<ChatsTab budgetId="b1" />)
    expect(screen.getByRole('button', { name: /Continue .* in the assistant/ })).toBeInTheDocument()
  })
})
