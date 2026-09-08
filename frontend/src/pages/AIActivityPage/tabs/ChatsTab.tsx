import { useState } from 'react'
import { ChevronDown, ChevronRight, MessageSquareText, PanelRightOpen, Trash2 } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import { useConversation, useConversations, useDeleteConversation } from '../../../api/aiChat'
import { useFormatters } from '../../../hooks/useFormatters'
import { confirmAsync } from '../../../stores/confirmStore'
import { ChatTranscript } from '../../../components/ai/chat/ChatTranscript'

/**
 * Past conversations.
 *
 * A row opens in place to the full transcript — the answers, what each one
 * looked up, and whether its figures were in the budget — so checking the
 * model's work does not require putting the conversation back in the panel.
 * "Continue" does that, for picking a thread back up.
 */
export function ChatsTab({ budgetId }: { budgetId: string }) {
  const { data, isLoading } = useConversations(budgetId)
  const remove = useDeleteConversation(budgetId)
  const { formatDate } = useFormatters()
  const [openId, setOpenId] = useState<string | null>(null)

  if (isLoading) return <div className="ai-activity__empty">Loading…</div>

  const conversations = data ?? []
  if (conversations.length === 0) {
    return (
      <div className="ai-activity__empty">
        No conversations yet. Open the assistant from the header and ask something about your
        budget.
      </div>
    )
  }

  return (
    <div className="ai-activity__list scroll-fill">
      {conversations.map((conversation) => {
        const open = openId === conversation.id
        const title = conversation.title ?? 'Untitled'
        return (
          <div key={conversation.id} className={`ai-chat ${open ? 'ai-chat--open' : ''}`}>
            <div className="ai-chat-row">
              <button
                type="button"
                className="ai-chat-row__open"
                onClick={() => setOpenId(open ? null : conversation.id)}
                aria-expanded={open}
              >
                {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                <MessageSquareText size={13} />
                <span className="ai-chat-row__title">{title}</span>
                <span className="ai-chat-row__meta">
                  {conversation.message_count} message
                  {conversation.message_count === 1 ? '' : 's'} ·{' '}
                  {formatDate(conversation.updated_at.slice(0, 10))}
                </span>
              </button>
              <ContinueButton conversationId={conversation.id} title={title} />
              <button
                type="button"
                className="ai-chat-row__delete"
                aria-label={`Delete ${title}`}
                title="Delete"
                onClick={async () => {
                  const ok = await confirmAsync({
                    title: 'Delete this conversation?',
                    message:
                      'The messages are removed. The model calls behind them stay in Model calls.',
                    confirmLabel: 'Delete',
                    destructive: true,
                  })
                  if (ok) await remove.mutateAsync(conversation.id)
                }}
              >
                <Trash2 size={13} />
              </button>
            </div>
            {open && <ConversationDetail budgetId={budgetId} conversationId={conversation.id} />}
          </div>
        )
      })}
    </div>
  )
}

/** Put the conversation back in the assistant panel, wherever it lives. */
function ContinueButton({ conversationId, title }: { conversationId: string; title: string }) {
  const setConversation = useUIStore((s) => s.setActiveConversation)
  const setPanelOpen = useUIStore((s) => s.setChatPanelOpen)
  return (
    <button
      type="button"
      className="ai-chat-row__continue"
      aria-label={`Continue ${title} in the assistant`}
      title="Continue in the assistant"
      onClick={() => {
        setConversation(conversationId)
        setPanelOpen(true)
      }}
    >
      <PanelRightOpen size={13} />
    </button>
  )
}

function ConversationDetail({
  budgetId,
  conversationId,
}: {
  budgetId: string
  conversationId: string
}) {
  const { data, isLoading } = useConversation(budgetId, conversationId)
  if (isLoading) return <div className="ai-chat__detail">Loading…</div>
  if (!data) return null
  return (
    <div className="ai-chat__detail">
      <ChatTranscript messages={data.messages} />
    </div>
  )
}
