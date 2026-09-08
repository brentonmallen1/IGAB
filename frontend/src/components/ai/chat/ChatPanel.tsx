import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Loader2, MessageSquarePlus, Send, Square, X } from 'lucide-react'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useAIStatus } from '../../../api/ai'
import { useConversation } from '../../../api/aiChat'
import { useChatStream } from './useChatStream'
import { describePage } from './pageContext'
import { ToolTrace } from './ToolTrace'
import { useChatPanelResize } from './useChatPanelResize'
import './ChatPanel.css'

/**
 * The assistant, beside the page rather than over it.
 *
 * In-flow rather than a floating drawer on purpose: the questions worth asking
 * here are about the figures on screen, and a panel that covers the register
 * hides the thing being discussed.
 */
export function ChatPanel() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const open = useUIStore((s) => s.chatPanelOpen)
  const width = useUIStore((s) => s.chatPanelWidth)
  const setOpen = useUIStore((s) => s.setChatPanelOpen)
  const conversationId = useUIStore((s) => s.activeConversationId)
  const setConversation = useUIStore((s) => s.setActiveConversation)
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const { data: status } = useAIStatus()
  const { pathname } = useLocation()
  const { handleProps } = useChatPanelResize()

  const [draft, setDraft] = useState('')
  const { turn, send, cancel } = useChatStream(budgetId)
  const { data: conversation } = useConversation(budgetId, conversationId)
  const bottom = useRef<HTMLDivElement>(null)

  const pageContext = useMemo(
    () => describePage({ pathname, selectedMonth }),
    [pathname, selectedMonth]
  )

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [turn.answer, turn.tools.length, conversation?.messages.length])

  if (!open || status?.enabled !== true) return null

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const message = draft.trim()
    if (!message || turn.streaming) return
    setDraft('')
    const id = await send(message, { conversationId, pageContext })
    if (id) setConversation(id)
  }

  const history = conversation?.messages ?? []
  // While a turn is streaming its own echo is authoritative; once it lands the
  // persisted messages take over, so a finished turn is never drawn twice.
  const showPending = turn.streaming || turn.error !== null

  return (
    <aside
      className="chat-panel"
      style={{ '--chat-panel-width': `${width}px` } as React.CSSProperties}
    >
      <div className="chat-panel__resize" {...handleProps} />

      <header className="chat-panel__header">
        <span className="chat-panel__title">Ask about your budget</span>
        <button
          type="button"
          className="chat-panel__icon"
          onClick={() => {
            cancel()
            setConversation(null)
          }}
          title="New conversation"
          aria-label="New conversation"
        >
          <MessageSquarePlus size={15} />
        </button>
        <button
          type="button"
          className="chat-panel__icon"
          onClick={() => setOpen(false)}
          title="Close"
          aria-label="Close chat"
        >
          <X size={15} />
        </button>
      </header>

      {turn.toolsAvailable === false && (
        <p className="chat-panel__notice">
          This model can’t look anything up, so it’s answering from the conversation alone. Pick a
          model that supports tools in System → AI.
        </p>
      )}

      <div className="chat-panel__scroll">
        {history.length === 0 && !showPending && (
          <div className="chat-panel__empty">
            <p>Ask about a month, an envelope, a payee, or where the money went.</p>
            <p className="chat-panel__empty-hint">
              It reads your budget through the same figures the app shows, and can’t change
              anything.
            </p>
          </div>
        )}

        {history.map((message) => (
          <div key={message.id} className={`chat-msg chat-msg--${message.role}`}>
            {message.role === 'assistant' && message.tool_calls && (
              <ToolTrace
                tools={message.tool_calls.map((t) => ({
                  name: t.name,
                  arguments: t.arguments,
                  resolved_arguments: t.resolved_arguments,
                  delegates_to: t.delegates_to,
                  rows: t.row_count,
                  truncated: t.truncated,
                  duration_ms: t.duration_ms,
                  error: t.error,
                }))}
              />
            )}
            <div className="chat-msg__body">{message.content}</div>
          </div>
        ))}

        {showPending && (
          <>
            <div className="chat-msg chat-msg--user">
              <div className="chat-msg__body">{turn.question}</div>
            </div>
            <div className="chat-msg chat-msg--assistant">
              <ToolTrace tools={turn.tools} />
              {turn.answer && <div className="chat-msg__body">{turn.answer}</div>}
              {turn.streaming && !turn.answer && (
                <div className="chat-msg__working">
                  <Loader2 size={13} className="chat-msg__spin" />
                  <span>{turn.tools.length > 0 ? 'Reading your budget…' : 'Thinking…'}</span>
                </div>
              )}
              {turn.error && <div className="chat-msg__error">{turn.error}</div>}
            </div>
          </>
        )}
        <div ref={bottom} />
      </div>

      <form className="chat-panel__composer" onSubmit={submit}>
        <textarea
          className="chat-panel__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void submit(e as unknown as React.FormEvent)
            }
          }}
          placeholder="Why is Groceries overspent?"
          rows={2}
          aria-label="Ask a question about your budget"
        />
        {turn.streaming ? (
          <button
            type="button"
            className="chat-panel__send"
            onClick={cancel}
            title="Stop"
            aria-label="Stop generating"
          >
            <Square size={14} />
          </button>
        ) : (
          <button
            type="submit"
            className="chat-panel__send"
            disabled={!draft.trim()}
            title="Send"
            aria-label="Send"
          >
            <Send size={14} />
          </button>
        )}
      </form>
    </aside>
  )
}
