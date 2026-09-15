import type { ConceptInfo, Signal } from '../../api/guide'
import { EmergencyFundPicker } from '../emergencyFund/EmergencyFundPicker'
import { SignalBindingSheet } from './SignalBindingSheet'

/**
 * Correcting one concept from the roadmap — the one mount every roadmap view
 * uses.
 *
 * The emergency fund is chosen, not bound: its envelopes are a tag, its
 * accounts a flag, and the picker writes both (plus what is kept elsewhere) in
 * one save. Every other concept keeps the binding sheet.
 */
export function SignalEditor({
  budgetId,
  concept,
  signal,
  onClose,
}: {
  budgetId: string
  concept: ConceptInfo
  signal: Signal | undefined
  onClose: () => void
}) {
  if (concept.key === 'emergency_fund') {
    return <EmergencyFundPicker budgetId={budgetId} from="guide" onClose={onClose} />
  }
  return (
    <SignalBindingSheet budgetId={budgetId} concept={concept} signal={signal} onClose={onClose} />
  )
}
