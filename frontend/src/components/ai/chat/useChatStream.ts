import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  streamChat,
  type ChatStreamEvent,
  type Grounding,
  type ToolCallEvent,
} from '../../../api/chatStream'
import { ROOT } from '../../../api/queryKeys'
import type { PageContext } from './pageContext'

export interface PendingTurn {
  /** What the user asked, echoed immediately. */
  question: string
  /** Prose so far. */
  answer: string
  thinking: string
  /** Tool calls in flight or finished, in order. */
  tools: ToolCallEvent[]
  usage: { prompt: number | null; eval: number | null } | null
  /** Whether the figures in the answer came from the budget. */
  grounding: Grounding | null
  error: string | null
  /** False when the model cannot look anything up. */
  toolsAvailable: boolean
  streaming: boolean
  /**
   * The persisted assistant message, once the server names it.
   *
   * The panel keeps drawing this turn until that id appears in the refetched
   * conversation. Hiding it the moment the stream ended made the answer vanish
   * for a whole round trip while the query caught up.
   */
  messageId: string | null
}

const EMPTY: PendingTurn = {
  question: '',
  answer: '',
  thinking: '',
  tools: [],
  usage: null,
  grounding: null,
  error: null,
  toolsAvailable: true,
  streaming: false,
  messageId: null,
}

/**
 * Fold one stream event into the turn.
 *
 * A table rather than a switch inside the loop: each case is independently
 * readable, and an event kind this client does not know about leaves the turn
 * untouched instead of needing a default branch.
 */
export function applyEvent(turn: PendingTurn, event: ChatStreamEvent): PendingTurn {
  switch (event.type) {
    case 'start':
      return { ...turn, toolsAvailable: event.tools }
    case 'thinking':
      return { ...turn, thinking: turn.thinking + event.delta }
    case 'token':
      return { ...turn, answer: turn.answer + event.delta }
    case 'tool_call':
      return {
        ...turn,
        tools: [...turn.tools, { name: event.name, arguments: event.arguments }],
      }
    case 'tool_result':
      return { ...turn, tools: withResult(turn.tools, event.result) }
    case 'usage':
      return { ...turn, usage: { prompt: event.prompt_tokens, eval: event.eval_tokens } }
    case 'grounding':
      return { ...turn, grounding: event.grounding }
    case 'error':
      return { ...turn, error: event.message }
    case 'done':
      return { ...turn, streaming: false, messageId: event.message_id }
  }
}

/**
 * Replace an announced tool call with its finished form.
 *
 * Matched from the end on name plus "has not resolved yet", so a model calling
 * the same tool twice in one turn updates the right one.
 */
function withResult(tools: ToolCallEvent[], result: ToolCallEvent): ToolCallEvent[] {
  const next = [...tools]
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].name === result.name && !next[i].resolved_arguments) {
      next[i] = result
      return next
    }
  }
  return [...next, result]
}

/**
 * Drives one streamed answer.
 *
 * The in-flight turn lives here rather than in React Query, which is for
 * server state that can be refetched — a half-received answer can not be.
 * Once the stream finishes, the conversation query is invalidated and the
 * persisted messages take over, so there is exactly one rendering of a
 * finished turn.
 */
export function useChatStream(budgetId: string | null) {
  const [turn, setTurn] = useState<PendingTurn>(EMPTY)
  const abort = useRef<AbortController | null>(null)
  const qc = useQueryClient()

  const cancel = useCallback(() => {
    abort.current?.abort()
    abort.current = null
    setTurn((t) => ({ ...t, streaming: false }))
  }, [])

  const reset = useCallback(() => setTurn(EMPTY), [])

  const send = useCallback(
    async (
      message: string,
      options: { conversationId: string | null; pageContext: PageContext | null }
    ): Promise<string | null> => {
      if (!budgetId) return null
      abort.current?.abort()
      const controller = new AbortController()
      abort.current = controller

      setTurn({ ...EMPTY, question: message, streaming: true })
      let conversationId = options.conversationId

      try {
        for await (const event of streamChat({
          budgetId,
          message,
          conversationId,
          pageContext: options.pageContext,
          clientToday: new Date().toISOString().slice(0, 10),
          signal: controller.signal,
        })) {
          setTurn((t) => applyEvent(t, event))
          if (event.type === 'start') conversationId = event.conversation_id
        }
      } catch (err) {
        // An abort is the user closing the panel, not a failure to report.
        if ((err as Error)?.name !== 'AbortError') {
          setTurn((t) => ({
            ...t,
            error: (err as Error)?.message ?? 'The chat stopped unexpectedly.',
            streaming: false,
          }))
        } else {
          setTurn((t) => ({ ...t, streaming: false }))
        }
      } finally {
        // Also covers a body that ended without a `done` frame, which would
        // otherwise latch `streaming` true and leave a spinner forever.
        setTurn((t) => (t.streaming ? { ...t, streaming: false } : t))
        abort.current = null
        qc.invalidateQueries({ queryKey: [ROOT.aiConversations] })
        qc.invalidateQueries({ queryKey: [ROOT.aiConversation] })
        qc.invalidateQueries({ queryKey: [ROOT.aiCalls] })
      }

      return conversationId
    },
    [budgetId, qc]
  )

  return { turn, send, cancel, reset }
}
