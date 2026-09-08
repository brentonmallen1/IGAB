import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Loader2, Send, Square } from 'lucide-react'
import { useIsTouch } from '../../../hooks/useMediaQuery'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useConversation } from '../../../api/aiChat'
import { useChatStream } from './useChatStream'
import { describePage } from './pageContext'
import { ToolTrace } from './ToolTrace'
import { ChatMarkdown } from './ChatMarkdown'
import { ChatTranscript, GroundingNote } from './ChatTranscript'
import { isAtBottom } from './stickToBottom'
import type { ChatTab } from './chatTabs'

const EXAMPLES = [
  'Why is Groceries overspent this month?',
  'Where did most of my money go in August?',
  'Who did I pay the most this year?',
  'Am I on track compared to what I budgeted?',
]

/**
 * One conversation: its history, the answer in flight, and the composer.
 *
 * Every open tab mounts one of these and the inactive ones are hidden, not
 * unmounted — the stream driving an answer lives in this component's hook,
 * and unmounting it would silently drop a reply that was still arriving
 * while you read another tab.
 */
export function ChatThread({
  budgetId,
  tab,
  active,
}: {
  budgetId: string | null
  tab: ChatTab
  active: boolean
}) {
  const assignConversation = useUIStore((s) => s.assignChatConversation)
  const labelTab = useUIStore((s) => s.labelChatTab)
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const { pathname } = useLocation()
  const isTouch = useIsTouch()

  const [draft, setDraft] = useState('')
  const { turn, send, cancel } = useChatStream(budgetId)
  const { data: conversation } = useConversation(budgetId, tab.conversationId)
  const composer = useRef<HTMLTextAreaElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const bottom = useRef<HTMLDivElement>(null)
  // Whether to keep following new content. Set on scroll, read on update — a
  // ref rather than state so tracking the scroll position does not re-render
  // the thread on every wheel event.
  const following = useRef(true)

  const pageContext = useMemo(
    () => describePage({ pathname, selectedMonth }),
    [pathname, selectedMonth]
  )

  // Also runs on becoming the visible tab: scrollIntoView is a no-op while
  // the thread is hidden, so an answer that finished in the background would
  // otherwise land with its end below the fold.
  useEffect(() => {
    if (active && following.current) bottom.current?.scrollIntoView({ block: 'end' })
  }, [active, turn.answer, turn.tools.length, conversation?.messages.length])

  // Landing the caret where you type — but only with a pointer. On touch
  // this would raise the keyboard over a sheet the user has not read yet,
  // and it would race BottomSheet's own initialFocus.
  useEffect(() => {
    if (active && !isTouch) composer.current?.focus()
  }, [active, isTouch])

  // A fresh chat learns its conversation id from the server's first event;
  // the tab follows it so the persisted history can load into this thread.
  useEffect(() => {
    if (turn.conversationId && turn.conversationId !== tab.conversationId) {
      assignConversation(tab.key, turn.conversationId)
    }
  }, [turn.conversationId, tab.conversationId, tab.key, assignConversation])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const message = draft.trim()
    if (!message || turn.streaming) return
    setDraft('')
    if (!tab.conversationId) labelTab(tab.key, message)
    await send(message, { conversationId: tab.conversationId, pageContext })
  }

  const history = conversation?.messages ?? []
  // The live turn is authoritative until the persisted one actually arrives.
  // Keying on `streaming` alone made the answer vanish the instant the stream
  // ended and reappear a round trip later, when the invalidated conversation
  // query came back.
  const landed = turn.messageId !== null && history.some((m) => m.id === turn.messageId)
  const showPending = turn.question !== '' && !landed
  // The server writes the user's message before it starts streaming, so once
  // the refetch lands it is in both places. Draw it once.
  const questionInHistory = history.some((m) => m.role === 'user' && m.content === turn.question)

  return (
    <div
      className="chat-thread"
      hidden={!active}
      role="tabpanel"
      id={`chat-thread-${tab.key}`}
      aria-labelledby={`chat-tab-${tab.key}`}
    >
      {turn.toolsAvailable === false && (
        <p className="chat-panel__notice">
          This model can’t look anything up, so it’s answering from the conversation alone. Pick a
          model that supports tools in System → AI.
        </p>
      )}

      <div
        className="chat-panel__scroll"
        ref={scroller}
        onScroll={() => {
          const el = scroller.current
          if (el) following.current = isAtBottom(el)
        }}
      >
        {history.length === 0 && !showPending && (
          <div className="chat-panel__empty">
            <p className="chat-panel__empty-lead">Try asking:</p>
            {/* Real questions, not topics: naming a subject teaches nobody the
                shape of a question that works. */}
            <ul className="chat-panel__examples">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button type="button" onClick={() => setDraft(example)}>
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <ChatTranscript messages={history} />

        {showPending && (
          <>
            {!questionInHistory && (
              <div className="chat-msg chat-msg--user">
                <div className="chat-msg__body">{turn.question}</div>
              </div>
            )}
            <div className="chat-msg chat-msg--assistant">
              <ToolTrace tools={turn.tools} />
              {turn.answer && (
                <div className="chat-msg__body">
                  <ChatMarkdown>{turn.answer}</ChatMarkdown>
                </div>
              )}
              {turn.streaming && !turn.answer && (
                <div className="chat-msg__working">
                  <Loader2 size={13} className="chat-msg__spin" />
                  <span>{turn.tools.length > 0 ? 'Reading your budget…' : 'Thinking…'}</span>
                </div>
              )}
              {!turn.streaming && <GroundingNote grounding={turn.grounding} />}
              {turn.error && (
                <div className="chat-msg__error">
                  <span>{turn.error}</span>
                  <button
                    type="button"
                    className="chat-msg__retry"
                    onClick={() =>
                      void send(turn.question, { conversationId: tab.conversationId, pageContext })
                    }
                  >
                    Try again
                  </button>
                </div>
              )}
            </div>
          </>
        )}
        <div ref={bottom} />
      </div>

      <form className="chat-panel__composer" onSubmit={submit}>
        <textarea
          ref={composer}
          className="chat-panel__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void submit(e as unknown as React.FormEvent)
            }
          }}
          placeholder="e.g. Why is Groceries overspent?"
          rows={2}
          aria-label="Ask a question about your budget"
          aria-describedby="chat-send-hint"
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
            title="Send (Enter)"
            aria-label="Send question"
          >
            <Send size={14} />
          </button>
        )}
      </form>
    </div>
  )
}
