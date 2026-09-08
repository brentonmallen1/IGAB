import { useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAICall, useAICalls, usePurgeCallPayloads, type AICall } from '../../../api/aiChat'
import { confirmAsync } from '../../../stores/confirmStore'

/**
 * Every request this app made to a model.
 *
 * The point is not completeness for its own sake. Small local models pick the
 * wrong tool and the wrong arguments, and a wrong argument produces a
 * confident wrong figure — so this is where you check what was actually asked
 * before believing what came back.
 */
export function ModelCallsTab({ budgetId }: { budgetId: string }) {
  const { data, isLoading } = useAICalls(budgetId, { limit: 100 })
  const purge = usePurgeCallPayloads(budgetId)

  async function handlePurge() {
    const ok = await confirmAsync({
      title: 'Delete stored prompts?',
      message:
        'This removes every stored prompt and response. The list of calls stays, so you can still see what ran and whether it worked.',
      confirmLabel: 'Delete prompts',
      destructive: true,
    })
    if (!ok) return
    const result = await purge.mutateAsync()
    toast.success(`Removed ${result.removed} stored prompt${result.removed === 1 ? '' : 's'}.`)
  }

  if (isLoading) return <div className="ai-activity__empty">Loading…</div>

  const calls = data?.calls ?? []
  if (calls.length === 0) {
    return (
      <div className="ai-activity__empty">
        No model calls yet. They appear here as soon as the AI does anything.
      </div>
    )
  }

  return (
    <>
      <div className="ai-activity__history-bar">
        <span className="ai-calls__count">
          {data?.total_count} call{data?.total_count === 1 ? '' : 's'}
        </span>
        <button type="button" className="ai-calls__purge" onClick={handlePurge}>
          <Trash2 size={12} />
          Delete stored prompts
        </button>
      </div>
      <div className="ai-activity__list scroll-fill">
        {calls.map((call) => (
          <CallRow key={call.id} call={call} budgetId={budgetId} />
        ))}
      </div>
    </>
  )
}

function CallRow({ call, budgetId }: { call: AICall; budgetId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="ai-call">
      <button
        type="button"
        className="ai-call__head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span className={`ai-call__status ai-call__status--${call.status}`}>
          {call.status === 'ok' ? '' : call.status}
        </span>
        <span className="ai-call__feature">{call.feature_label}</span>
        <span className="ai-call__model">{call.model}</span>
        {call.tool_call_count > 0 && (
          <span className="ai-call__tools">
            {call.tool_call_count} lookup{call.tool_call_count === 1 ? '' : 's'}
          </span>
        )}
        {call.duration_ms != null && <span className="ai-call__ms">{call.duration_ms}ms</span>}
        {call.prompt_tokens != null && (
          <span className="ai-call__tokens">
            {call.prompt_tokens}↑ {call.completion_tokens ?? 0}↓
          </span>
        )}
      </button>
      {call.error && (
        <div className="ai-call__error">
          <AlertTriangle size={12} /> {call.error}
        </div>
      )}
      {open && <CallDetail budgetId={budgetId} callId={call.id} />}
    </div>
  )
}

function CallDetail({ budgetId, callId }: { budgetId: string; callId: string }) {
  const { data, isLoading } = useAICall(budgetId, callId)
  if (isLoading) return <div className="ai-call__detail">Loading…</div>
  if (!data) return null

  if (data.payload_pruned) {
    return (
      <div className="ai-call__detail">
        {/* Aged out, not never recorded — saying which matters. */}
        <p className="ai-call__pruned">
          The prompt and response for this call have aged out of retention. The call itself is still
          recorded above.
        </p>
      </div>
    )
  }

  return (
    <div className="ai-call__detail">
      {data.tool_trace.length > 0 && (
        <section>
          <h4>What it looked up</h4>
          <ul className="ai-call__trace">
            {data.tool_trace.map((tool, i) => (
              <li key={`${tool.name}-${i}`}>
                <strong>{tool.name}</strong>
                <div>
                  asked for: <code>{JSON.stringify(tool.arguments)}</code>
                </div>
                {tool.resolved_arguments &&
                  JSON.stringify(tool.resolved_arguments) !== JSON.stringify(tool.arguments) && (
                    <div className="ai-call__changed">
                      actually ran: <code>{JSON.stringify(tool.resolved_arguments)}</code>
                    </div>
                  )}
                {tool.delegates_to && <div>via {tool.delegates_to}</div>}
                {tool.error && <div className="ai-call__changed">{tool.error}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.system && (
        <section>
          <h4>System prompt</h4>
          <pre>{data.system}</pre>
        </section>
      )}

      {data.messages.length > 0 && (
        <section>
          <h4>Sent</h4>
          <pre>
            {data.messages
              .map((m) => `${m.role}: ${typeof m.content === 'string' ? m.content : ''}`)
              .join('\n\n')}
          </pre>
        </section>
      )}

      {data.thinking && (
        <section>
          <h4>Thinking</h4>
          <pre>{data.thinking}</pre>
        </section>
      )}

      {data.response && (
        <section>
          <h4>Answer</h4>
          <pre>{data.response}</pre>
        </section>
      )}
    </div>
  )
}
