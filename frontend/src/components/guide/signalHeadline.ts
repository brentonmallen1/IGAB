import type { ConceptInfo, Signal } from '../../api/guide'

export type SignalKind = ConceptInfo['kind']

/**
 * A signal figure in the concept's own units — money for an amount, a
 * percentage for a rate. Null when there is no figure, or it does not parse.
 */
export function formatSignalFigure(
  raw: string | null,
  kind: SignalKind,
  formatMoney: (n: number) => string
): string | null {
  if (raw === null) return null
  const n = Number(raw)
  if (Number.isNaN(n)) return null
  return kind === 'rate' ? `${n.toFixed(1)}%` : formatMoney(n)
}

export interface SignalHeadline {
  text: string
  /** False when the app could not tell — shown muted, never as a figure. */
  known: boolean
}

/**
 * What stands beside a signal's label.
 *
 * A measured concept (an amount, a rate) reads its figure. A boolean one has
 * no figure — its whole answer is `met` — so it reads yes or no. Reading the
 * figure for every kind is what put "not known" above "you have a budget".
 */
export function signalHeadline(
  signal: Pick<Signal, 'met' | 'value'>,
  kind: SignalKind,
  formatMoney: (n: number) => string
): SignalHeadline {
  if (kind === 'boolean') {
    if (signal.met === true) return { text: 'yes', known: true }
    if (signal.met === false) return { text: 'no', known: true }
    return { text: 'not known', known: false }
  }
  const figure = formatSignalFigure(signal.value, kind, formatMoney)
  return figure === null ? { text: 'not known', known: false } : { text: figure, known: true }
}
