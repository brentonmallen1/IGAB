import { useState } from 'react'
import { ChevronDown, ChevronRight, Wrench } from 'lucide-react'
import type { ToolCallEvent } from '../../../api/chatStream'

/**
 * What the model looked up, and with what.
 *
 * This is not debug output. A small local model picks the wrong tool and the
 * wrong arguments, and a wrong argument produces a confident wrong number — so
 * the lookup is the thing to check, and it belongs next to the answer it
 * produced rather than only in a log somewhere else.
 *
 * The arguments the model *wrote* are shown beside the ones that actually ran,
 * because the difference between them is exactly where a bad model is visible.
 */
export function ToolTrace({ tools }: { tools: ToolCallEvent[] }) {
  const [open, setOpen] = useState(false)
  if (tools.length === 0) return null

  const failed = tools.filter((t) => t.error).length

  return (
    <div className="chat-tools">
      <button
        type="button"
        className="chat-tools__toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Wrench size={12} />
        <span>
          Looked up {tools.length} {tools.length === 1 ? 'thing' : 'things'}
          {failed > 0 ? ` · ${failed} failed` : ''}
        </span>
      </button>

      {open && (
        <ul className="chat-tools__list">
          {tools.map((tool, i) => (
            <li key={`${tool.name}-${i}`} className="chat-tools__item">
              <div className="chat-tools__name">
                {tool.name}
                {tool.duration_ms != null && (
                  <span className="chat-tools__ms">{tool.duration_ms}ms</span>
                )}
              </div>

              <Args label="Asked for" value={tool.arguments} />
              {tool.resolved_arguments &&
                JSON.stringify(tool.resolved_arguments) !== JSON.stringify(tool.arguments) && (
                  <Args label="Actually ran" value={tool.resolved_arguments} changed />
                )}

              {tool.delegates_to && <div className="chat-tools__via">via {tool.delegates_to}</div>}
              {tool.rows != null && (
                <div className="chat-tools__rows">
                  {tool.rows} {tool.rows === 1 ? 'row' : 'rows'}
                  {tool.truncated ? ' (showing some)' : ''}
                </div>
              )}
              {tool.error && <div className="chat-tools__error">{tool.error}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Args({
  label,
  value,
  changed = false,
}: {
  label: string
  value: Record<string, unknown>
  changed?: boolean
}) {
  const entries = Object.entries(value ?? {})
  if (entries.length === 0) return null
  return (
    <div className={`chat-tools__args ${changed ? 'chat-tools__args--changed' : ''}`}>
      <span className="chat-tools__args-label">{label}</span>
      <code>{entries.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ')}</code>
    </div>
  )
}
