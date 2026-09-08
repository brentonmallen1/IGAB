import { MessageSquarePlus, X } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useAIStatus } from '../../../api/ai'
import { useConversations } from '../../../api/aiChat'
import { ChatThread } from './ChatThread'
import { useChatPanelResize } from './useChatPanelResize'
import './ChatPanel.css'

/**
 * The assistant, beside the page rather than over it.
 *
 * In-flow rather than a floating drawer on purpose: the questions worth asking
 * here are about the figures on screen, and a panel that covers the register
 * hides the thing being discussed.
 *
 * Conversations are tabs. Each keeps its own thread mounted, so an answer
 * keeps arriving in one while you ask something else in another.
 */
export function ChatPanel() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const open = useUIStore((s) => s.chatPanelOpen)
  const width = useUIStore((s) => s.chatPanelWidth)
  const setOpen = useUIStore((s) => s.setChatPanelOpen)
  const tabs = useUIStore((s) => s.chatTabs)
  const activeKey = useUIStore((s) => s.activeChatTab)
  const newTab = useUIStore((s) => s.newChatTab)
  const selectTab = useUIStore((s) => s.selectChatTab)
  const closeTab = useUIStore((s) => s.closeChatTab)
  const { data: status } = useAIStatus()
  const { data: conversations } = useConversations(budgetId)
  const { handleProps } = useChatPanelResize()
  const isMobile = useIsMobile()

  if (!open || status?.enabled !== true) return null

  // The server's title once the list has it, the first question until then,
  // and a placeholder before either.
  function titleOf(tab: (typeof tabs)[number]): string {
    const listed = conversations?.find((c) => c.id === tab.conversationId)?.title
    return listed ?? tab.label ?? 'New chat'
  }

  const body = (
    <>
      {/* The sheet draws its own title and close button on mobile, so only the
          action it does not provide is repeated there. */}
      <header className="chat-panel__header">
        {!isMobile && <span className="chat-panel__title">Ask about your budget</span>}
        <button
          type="button"
          className="chat-panel__icon"
          onClick={newTab}
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

      {/* Hidden while there is only one, unnamed chat: a strip with a single
          "New chat" tab is chrome explaining nothing. */}
      {(tabs.length > 1 || tabs[0]?.label || tabs[0]?.conversationId) && (
        <div className="chat-tabs" role="tablist" aria-label="Open conversations">
          {tabs.map((tab) => {
            const active = tab.key === activeKey
            const title = titleOf(tab)
            return (
              <div key={tab.key} className={`chat-tab ${active ? 'chat-tab--active' : ''}`}>
                <button
                  type="button"
                  role="tab"
                  id={`chat-tab-${tab.key}`}
                  className="chat-tab__select"
                  aria-selected={active}
                  aria-controls={`chat-thread-${tab.key}`}
                  title={title}
                  onClick={() => selectTab(tab.key)}
                >
                  {title}
                </button>
                <button
                  type="button"
                  className="chat-tab__close"
                  aria-label={`Close ${title}`}
                  onClick={() => closeTab(tab.key)}
                >
                  <X size={11} />
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Stays put rather than living in an empty state the first question
          destroys: "it cannot move your money" is a trust property, and it is
          most worth reading beside an answer suggesting that you do. */}
      <p className="chat-panel__standing-note" id="chat-send-hint">
        Reads your budget and suggests — it can’t move money. Enter sends.
      </p>

      {tabs.map((tab) => (
        <ChatThread key={tab.key} budgetId={budgetId} tab={tab} active={tab.key === activeKey} />
      ))}
    </>
  )

  // The same body in the app's sheet on a phone, which is where the focus
  // trap, the overlay-stack registration Escape reads, Android-back
  // dismissal and the safe-area insets come from. Closing the sheet hides
  // the threads; it does not stop an answer that is still arriving.
  if (isMobile) {
    return (
      <BottomSheet
        open
        onClose={() => setOpen(false)}
        title="Ask about your budget"
        height="full"
        historyKey="ai-chat"
        closeLabel="Close the assistant"
      >
        <div className="chat-panel chat-panel--sheet">{body}</div>
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
      {body}
    </aside>
  )
}
