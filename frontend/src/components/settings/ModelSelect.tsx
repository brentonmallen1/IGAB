import type { OllamaModel } from '../../api/ai'
import { sameOllamaModel } from '../../api/ai'
import { formatTokens, modelOptions, type Capability } from './modelChoice'

/**
 * One control for "which model does this job".
 *
 * A select rather than a wall of tiles: the page has three of these now
 * (main, receipts, assistant), and three scrolling tile lists would have
 * pushed everything below them off the screen. What the chosen model can
 * do is said underneath, from the same probe the workers gate on.
 */
export function ModelSelect({
  id,
  value,
  onChange,
  models,
  require,
  placeholder = 'Choose a model…',
  disabled = false,
}: {
  id: string
  value: string
  onChange: (name: string) => void
  models: OllamaModel[] | undefined
  /** A capability the job needs; models without it are listed but disabled. */
  require?: Capability
  placeholder?: string
  disabled?: boolean
}) {
  const options = modelOptions(models, value, require)
  const selected = models?.find((m) => sameOllamaModel(m.name, value))
  // The select's value must be one of its options, and the saved value may
  // be spelled "gemma4" while the server lists "gemma4:latest".
  const current = options.find((o) => sameOllamaModel(o.value, value))?.value ?? ''

  return (
    <div className="model-select">
      <select
        id={id}
        className="settings-select model-select__control"
        value={current}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        <option value="" disabled>
          {placeholder}
        </option>
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      {selected && (selected.capabilities.length > 0 || selected.context_length) && (
        <span className="model-select__caps">
          {selected.capabilities.map((c) => (
            <span
              key={c}
              className={`ai-panel__cap ${require === c ? 'ai-panel__cap--required' : ''}`}
            >
              {c}
            </span>
          ))}
          {selected.context_length && (
            <span className="ai-panel__cap" title="Maximum context the model reports">
              {formatTokens(selected.context_length)} context
            </span>
          )}
        </span>
      )}
    </div>
  )
}
