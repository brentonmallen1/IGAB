/**
 * Choosing a model for a job, and saying what it can do.
 *
 * Pure so the rules are one-line tests: which models a picker may offer for
 * a job that needs a capability, how a context length reads, and which
 * window sizes make sense for a given model.
 */
import type { OllamaModel } from '../../api/ai'
import { sameOllamaModel } from '../../api/ai'
import { formatBytes } from '../../utils/formatBytes'

export type Capability = 'vision' | 'tools'

export interface ModelOption {
  value: string
  label: string
  /** The job needs a capability the server says this model lacks. */
  disabled: boolean
}

/**
 * A model can be offered for a job unless the server has said it cannot do
 * it. An empty capability list is "unknown", not "none" — an older Ollama
 * reports nothing, and refusing every model then would leave the picker
 * empty on exactly the installs that need it most.
 */
export function canDo(model: OllamaModel, capability: Capability | undefined): boolean {
  if (!capability) return true
  if (model.capabilities.length === 0) return true
  return model.capabilities.includes(capability)
}

export function formatTokens(tokens: number): string {
  if (tokens >= 1024 && tokens % 1024 === 0) return `${tokens / 1024}k`
  return tokens.toLocaleString()
}

/**
 * The picker's options: every model the server lists, plus the saved value
 * when the list does not carry it (Ollama down, or a model since removed) so
 * the control never shows a blank for a setting that is set.
 */
export function modelOptions(
  models: OllamaModel[] | undefined,
  selected: string,
  require?: Capability
): ModelOption[] {
  const options = (models ?? []).map((m) => ({
    value: m.name,
    label: describe(m, require),
    disabled: !canDo(m, require),
  }))
  if (selected && !options.some((o) => sameOllamaModel(o.value, selected))) {
    options.unshift({ value: selected, label: `${selected} (not on this server)`, disabled: false })
  }
  return options
}

function describe(m: OllamaModel, require?: Capability): string {
  const bits = [m.name]
  if (m.size > 0) bits.push(formatBytes(m.size))
  if (require && m.capabilities.length > 0 && !m.capabilities.includes(require)) {
    bits.push(`no ${require}`)
  }
  return bits.join(' · ')
}

/** The values the context-window picker offers. */
export const CONTEXT_CHOICES = [8_192, 16_384, 32_768, 65_536, 131_072] as const

/**
 * Window sizes worth offering for a model: "auto", then every standard size
 * the model can take. Nothing above what it reports — asking for more than
 * the model supports is a silent clamp on the server, which is a setting
 * that lies.
 */
export function contextChoices(modelMax: number | null): number[] {
  return CONTEXT_CHOICES.filter((n) => modelMax === null || n <= modelMax)
}

/**
 * One window setting serves every job's model, so it offers only what all
 * of them can take — the smallest maximum any of them reports.
 */
export function sharedContextChoices(modelMaxes: (number | null | undefined)[]): number[] {
  const known = modelMaxes.filter((n): n is number => typeof n === 'number' && n > 0)
  return contextChoices(known.length ? Math.min(...known) : null)
}

/**
 * The Auto option's label. Auto is sized per model on the server, so it
 * names a number only when every job's model resolved to the same one.
 */
export function autoWindowLabel(windows: (number | null | undefined)[]): string {
  const known = [...new Set(windows.filter((n): n is number => typeof n === 'number' && n > 0))]
  if (known.length === 1) return `Auto (${formatTokens(known[0])})`
  return known.length ? 'Auto (sized for each model)' : 'Auto (sized from the model)'
}

/** "asks for 32k of its 128k context" — the window a job's model is given. */
export function windowNote(numCtx: number | null, modelMax: number | null): string | null {
  return numCtx && modelMax
    ? `asks for ${formatTokens(numCtx)} of its ${formatTokens(modelMax)} context`
    : null
}
