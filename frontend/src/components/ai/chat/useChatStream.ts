import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { streamChat, type ToolCallEvent } from '../../../api/chatStream'
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
  error: string | null
  /** False when the model cannot look anything up. */
  toolsAvailable: boolean
  streaming: boolean
}

const EMPTY: PendingTurn = {
  question: '',
  answer: '',
  thinking: '',
  tools: [],
  usage: null,
  error: null,
  toolsAvailable: true,
  streaming: false,
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
          switch (event.type) {
            case 'start':
              conversationId = event.conversation_id
              setTurn((t) => ({ ...t, toolsAvailable: event.tools }))
              break
            case 'thinking':
              setTurn((t) => ({ ...t, thinking: t.thinking + event.delta }))
              break
            case 'token':
              setTurn((t) => ({ ...t, answer: t.answer + event.delta }))
              break
            case 'tool_call':
              setTurn((t) => ({
                ...t,
                tools: [...t.tools, { name: event.name, arguments: event.arguments }],
              }))
              break
            case 'tool_result':
              // Replace the announced call with the finished one, matching on
              // the last entry with that name and no result yet.
              setTurn((t) => {
                const tools = [...t.tools]
                for (let i = tools.length - 1; i >= 0; i -= 1) {
                  if (tools[i].name === event.result.name && !tools[i].resolved_arguments) {
                    tools[i] = event.result
                    return { ...t, tools }
                  }
                }
                return { ...t, tools: [...tools, event.result] }
              })
              break
            case 'usage':
              setTurn((t) => ({
                ...t,
                usage: { prompt: event.prompt_tokens, eval: event.eval_tokens },
              }))
              break
            case 'error':
              setTurn((t) => ({ ...t, error: event.message }))
              break
            case 'done':
              setTurn((t) => ({ ...t, streaming: false }))
              break
          }
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
