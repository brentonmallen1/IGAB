import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStream } from './useChatStream'
import type { ChatStreamEvent } from '../../../api/chatStream'

const streamChat = vi.hoisted(() => vi.fn())
vi.mock('../../../api/chatStream', () => ({ streamChat }))

function scripted(events: ChatStreamEvent[]) {
  return async function* () {
    for (const event of events) yield event
  }
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('useChatStream', () => {
  beforeEach(() => {
    streamChat.mockReset()
  })

  it('assembles prose from token deltas', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'start', conversation_id: 'c1', tools: true },
        { type: 'token', delta: 'Groceries is ' },
        { type: 'token', delta: 'over by $42.' },
        { type: 'done', message_id: 'm1' },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('why?', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.answer).toBe('Groceries is over by $42.')
    expect(result.current.turn.streaming).toBe(false)
  })

  it('returns the conversation id the server assigned', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'start', conversation_id: 'c-new', tools: true },
        { type: 'done', message_id: null },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    let id: string | null = null
    await act(async () => {
      id = await result.current.send('hi', { conversationId: null, pageContext: null })
    })
    expect(id).toBe('c-new')
  })

  it('keeps thinking separate from the answer', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'thinking', delta: 'checking the grid' },
        { type: 'token', delta: 'Two shops.' },
        { type: 'done', message_id: 'm1' },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('why?', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.thinking).toBe('checking the grid')
    expect(result.current.turn.answer).toBe('Two shops.')
  })

  it('upgrades an announced tool call with its result', async () => {
    // The panel shows what it reached for while it runs, then what came back —
    // one entry, not two.
    streamChat.mockImplementation(
      scripted([
        { type: 'tool_call', name: 'spending_by_category', arguments: { months: '3' } },
        {
          type: 'tool_result',
          result: {
            name: 'spending_by_category',
            arguments: { months: '3' },
            resolved_arguments: { months: 3 },
            rows: 12,
            truncated: false,
          },
        },
        { type: 'done', message_id: 'm1' },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.tools).toHaveLength(1)
    expect(result.current.turn.tools[0].resolved_arguments).toEqual({ months: 3 })
  })

  it('records a result whose call was never announced', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'tool_result', result: { name: 'orphan', arguments: {}, rows: 0 } },
        { type: 'done', message_id: 'm1' },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.tools).toHaveLength(1)
  })

  it('reports that the model cannot look anything up', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'start', conversation_id: 'c1', tools: false },
        { type: 'done', message_id: null },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.toolsAvailable).toBe(false)
  })

  it('keeps token counts', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'usage', prompt_tokens: 820, eval_tokens: 140 },
        { type: 'done', message_id: 'm1' },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.usage).toEqual({ prompt: 820, eval: 140 })
  })

  it('surfaces an error event', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'error', message: 'Could not reach Ollama.' },
        { type: 'done', message_id: null },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.error).toBe('Could not reach Ollama.')
  })

  it('surfaces a transport failure', async () => {
    streamChat.mockImplementation(() => {
      throw new Error('The chat could not start (500).')
    })
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.error).toContain('500')
    expect(result.current.turn.streaming).toBe(false)
  })

  it('treats an abort as a stop, not a failure', async () => {
    // Closing the panel mid-answer is the user's choice, not an error to
    // report back at them.
    streamChat.mockImplementation(() => {
      const err = new Error('aborted')
      err.name = 'AbortError'
      throw err
    })
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    expect(result.current.turn.error).toBeNull()
    expect(result.current.turn.streaming).toBe(false)
  })

  it('does nothing without a budget', async () => {
    const { result } = renderHook(() => useChatStream(null), { wrapper })
    let id: string | null = 'unset'
    await act(async () => {
      id = await result.current.send('q', { conversationId: null, pageContext: null })
    })
    expect(id).toBeNull()
    expect(streamChat).not.toHaveBeenCalled()
  })

  it('cancel stops the stream', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'token', delta: 'partial' },
        { type: 'done', message_id: null },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    act(() => result.current.cancel())
    await waitFor(() => expect(result.current.turn.streaming).toBe(false))
  })

  it('reset clears the turn', async () => {
    streamChat.mockImplementation(
      scripted([
        { type: 'token', delta: 'hello' },
        { type: 'done', message_id: null },
      ])
    )
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', { conversationId: null, pageContext: null })
    })
    act(() => result.current.reset())
    expect(result.current.turn.answer).toBe('')
    expect(result.current.turn.question).toBe('')
  })

  it('sends the page context and today', async () => {
    streamChat.mockImplementation(scripted([{ type: 'done', message_id: null }]))
    const { result } = renderHook(() => useChatStream('b1'), { wrapper })
    await act(async () => {
      await result.current.send('q', {
        conversationId: 'c1',
        pageContext: { kind: 'budget', month: '2026-09-01' },
      })
    })
    expect(streamChat).toHaveBeenCalledWith(
      expect.objectContaining({
        budgetId: 'b1',
        conversationId: 'c1',
        pageContext: { kind: 'budget', month: '2026-09-01' },
        clientToday: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      })
    )
  })
})
