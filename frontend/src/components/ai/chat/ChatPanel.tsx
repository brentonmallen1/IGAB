import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Loader2, MessageSquarePlus, Send, Square, X } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { useIsMobile, useIsTouch } from '../../../hooks/useMediaQuery'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useAIStatus } from '../../../api/ai'
import { useConversation } from '../../../api/aiChat'
import { useChatStream } from './useChatStream'
import { describePage } from './pageContext'
import { ToolTrace } from './ToolTrace'
import { ChatMarkdown } from './ChatMarkdown'
import { ChatTranscript, GroundingNote } from './ChatTranscript'
import { useChatPanelResize } from './useChatPanelResize'
import { isAtBottom } from './stickToBottom'
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
  const isMobile = useIsMobile()
  const isTouch = useIsTouch()

  const [draft, setDraft] = useState('')
  const { turn, send, cancel, reset } = useChatStream(budgetId)
  const { data: conversation } = useConversation(budgetId, conversationId)
  const composer = useRef<HTMLTextAreaElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const bottom = useRef<HTMLDivElement>(null)
  // Whether to keep following new content. Set on scroll, read on update — a
  // ref rather than state so tracking the scroll position does not re-render
  // the panel on every wheel event.
  const following = useRef(true)

  const pageContext = useMemo(
    () => describePage({ pathname, selectedMonth }),
    [pathname, selectedMonth]
  )

  useEffect(() => {
    if (following.current) bottom.current?.scrollIntoView({ block: 'end' })
  }, [turn.answer, turn.tools.length, conversation?.messages.length])

  // Opening the panel should land the caret where you type, rather than
  // leaving focus on a toggle three columns away — but only with a pointer.
  // On touch this would raise the keyboard over a sheet the user has not read
  // yet, and it would race BottomSheet's own initialFocus. QuickAddSheet made
  // the same call for the same reason.
  useEffect(() => {
    if (open && !isTouch) composer.current?.focus()
  }, [open, isTouch])

  // Keep the live turn and the selected conversation about the same chat.
  // A fresh question gets its conversation id from the server's first event,
  // so the selection follows it; when the selection moves away — the Chats
  // tab opening an older one, or the store being cleared — the finished turn
  // is dropped rather than drawn under someone else's history. Without this
  // "New conversation" cleared the id and changed nothing on screen.
  useEffect(() => {
    if (!turn.conversationId || turn.conversationId === conversationId) return
    if (turn.streaming) setConversation(turn.conversationId)
    else reset()
  }, [turn.conversationId, turn.streaming, conversationId, setConversation, reset])

  if (!open || status?.enabled !== true) return null

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const message = draft.trim()
    if (!message || turn.streaming) return
    setDraft('')
    await send(message, { conversationId, pageContext })
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

  const conversationBody = (
    <>
      {/* The sheet draws its own title and close button on mobile, so only the
          action it does not provide is repeated there. */}
      <header className="chat-panel__header">
        {!isMobile && <span className="chat-panel__title">Ask about your budget</span>}
        <button
          type="button"
          className="chat-panel__icon"
          onClick={() => {
            cancel()
            reset()
            setConversation(null)
            if (!isTouch) composer.current?.focus()
          }}
          title="New conversation"
          aria-label="Start a new conversation"
        >
          <MessageSquarePlus size={15} />
        </button>
        {!isMobile && (
          <button
            type="button"
            className="chat-panel__icon"
            onClick={() => setOpen(false)}
            title="Close"
            aria-label="Close the assistant"
          >
            <X size={15} />
          </button>
        )}
      </header>

      {/* Stays put rather than living in an empty state the first question
          destroys: "it cannot move your money" is a trust property, and it is
          most worth reading beside an answer suggesting that you do. */}
      <p className="chat-panel__standing-note" id="chat-send-hint">
        Reads your budget and suggests — it can’t move money. Enter sends.
      </p>

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
              {[
                'Why is Groceries overspent this month?',
                'Where did most of my money go in August?',
                'Who did I pay the most this year?',
                'Am I on track compared to what I budgeted?',
              ].map((example) => (
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
                    onClick={() => void send(turn.question, { conversationId, pageContext })}
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
    </>
  )

  // The same body in the app's sheet on a phone, which is where the focus
  // trap, the overlay-stack registration Escape reads, Android-back
  // dismissal and the safe-area insets come from.
  if (isMobile) {
    return (
      <BottomSheet
        open
        onClose={() => {
          cancel()
          setOpen(false)
        }}
        title="Ask about your budget"
        height="full"
        historyKey="ai-chat"
        closeLabel="Close the assistant"
      >
        <div className="chat-panel chat-panel--sheet">{conversationBody}</div>
      </BottomSheet>
    )
  }

  return (
    <aside
      className="chat-panel"
      aria-label="Budget assistant"
      style={{ '--chat-panel-width': `${width}px` } as React.CSSProperties}
    >
      <div className="chat-panel__resize" {...handleProps} />
      {conversationBody}
    </aside>
  )
}
