import { MessageSquareText, Trash2 } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import { useConversations, useDeleteConversation } from '../../../api/aiChat'
import { useFormatters } from '../../../hooks/useFormatters'
import { confirmAsync } from '../../../stores/confirmStore'

/** Past conversations. Opening one puts it back in the panel. */
export function ChatsTab({ budgetId }: { budgetId: string }) {
  const { data, isLoading } = useConversations(budgetId)
  const remove = useDeleteConversation(budgetId)
  const setConversation = useUIStore((s) => s.setActiveConversation)
  const setPanelOpen = useUIStore((s) => s.setChatPanelOpen)
  const { formatDate } = useFormatters()

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
      {conversations.map((conversation) => (
        <div key={conversation.id} className="ai-chat-row">
          <button
            type="button"
            className="ai-chat-row__open"
            onClick={() => {
              setConversation(conversation.id)
              setPanelOpen(true)
            }}
          >
            <MessageSquareText size={13} />
            <span className="ai-chat-row__title">{conversation.title ?? 'Untitled'}</span>
            <span className="ai-chat-row__meta">
              {conversation.message_count} message{conversation.message_count === 1 ? '' : 's'} ·{' '}
              {formatDate(conversation.updated_at.slice(0, 10))}
            </span>
          </button>
          <button
            type="button"
            className="ai-chat-row__delete"
            aria-label={`Delete ${conversation.title ?? 'conversation'}`}
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
      ))}
    </div>
  )
}
