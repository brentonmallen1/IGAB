import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ConceptInfo } from '../../api/guide'

vi.mock('../emergencyFund/EmergencyFundPicker', () => ({
  EmergencyFundPicker: ({ from }: { from?: string }) => <div>picker from {from}</div>,
}))
vi.mock('./SignalBindingSheet', () => ({
  SignalBindingSheet: ({ concept }: { concept: ConceptInfo }) => <div>sheet for {concept.key}</div>,
}))

import { SignalEditor } from './SignalEditor'

const concept = (key: ConceptInfo['key']): ConceptInfo => ({
  key,
  label: key,
  kind: 'amount',
  binds_to: [],
  prompt: '',
  caveat: '',
  auto: true,
  allows_external: true,
  us_only: false,
  aliases: [],
})

describe('SignalEditor', () => {
  it('sends the emergency fund to the picker, as the Guide', () => {
    render(
      <SignalEditor
        budgetId="b1"
        concept={concept('emergency_fund')}
        signal={undefined}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByText('picker from guide')).toBeInTheDocument()
  })

  it('sends every other concept to the binding sheet', () => {
    render(
      <SignalEditor budgetId="b1" concept={concept('hsa')} signal={undefined} onClose={vi.fn()} />
    )
    expect(screen.getByText('sheet for hsa')).toBeInTheDocument()
  })
})
