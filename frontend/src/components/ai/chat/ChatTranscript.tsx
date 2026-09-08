import { AlertTriangle } from 'lucide-react'
import type { ChatMessage } from '../../../api/aiChat'
import { ToolTrace } from './ToolTrace'
import { ChatMarkdown } from './ChatMarkdown'
import { groundingNote } from './groundingNote'
import './ChatTranscript.css'

/**
 * Whether an answer's figures came from the budget.
 *
 * Sits under the answer rather than in the tool disclosure: it is about the
 * text you just read, and a warning folded behind a chevron is a warning
 * nobody sees.
 */
export function GroundingNote({ grounding }: { grounding: Parameters<typeof groundingNote>[0] }) {
  const note = groundingNote(grounding)
  if (note.tone === 'none') return null
  return (
    <p
      className={`chat-grounding chat-grounding--${note.tone}`}
      role={note.tone === 'warn' ? 'status' : undefined}
    >
      {note.tone === 'warn' && <AlertTriangle size={12} aria-hidden />}
      <span>{note.text}</span>
    </p>
  )
}

/**
 * The persisted messages of one conversation.
 *
 * One rendering for both places a past conversation appears — the assistant
 * panel and the Chats tab of AI Activity. What the model looked up, the
 * answer, and whether its figures were in the budget travel together; a
 * second transcript that dropped one of them would be the one people read
 * when checking the model's work.
 */
export function ChatTranscript({ messages }: { messages: ChatMessage[] }) {
  return (
    <>
      {messages.map((message) => (
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
          <div className="chat-msg__body">
            {message.role === 'assistant' ? (
              <ChatMarkdown>{message.content}</ChatMarkdown>
            ) : (
              message.content
            )}
          </div>
          {message.role === 'assistant' && <GroundingNote grounding={message.grounding} />}
        </div>
      ))}
    </>
  )
}
