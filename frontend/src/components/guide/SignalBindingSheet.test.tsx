/**
 * The binding sheet reopens with the amount a person declared holding
 * elsewhere. The server sends that figure as a JSON number; the type said
 * string, the input was seeded with the number, and every save — Save, Reset,
 * Don't track — threw on `.trim()` and said "Could not save that".
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ConceptInfo, Signal } from '../../api/guide'
import { SignalBindingSheet } from './SignalBindingSheet'

const { mutateAsync } = vi.hoisted(() => ({ mutateAsync: vi.fn() }))

vi.mock('../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/guide')>()),
  useConceptCandidates: () => ({ data: { category: [] } }),
  useSetBinding: () => ({ mutateAsync, isPending: false }),
}))

const concept: ConceptInfo = {
  key: 'emergency_fund',
  label: 'Emergency fund',
  kind: 'amount',
  binds_to: ['category'],
  prompt: 'Which categories hold it?',
  caveat: '',
  auto: true,
  allows_external: true,
  us_only: false,
  aliases: [],
}

function signal(over: Partial<Signal> = {}): Signal {
  return {
    key: 'emergency_fund',
    tracked: true,
    source: 'external',
    met: false,
    value: 1250,
    detected_value: 0,
    external_value: 1250,
    external_declared: true,
    external_as_of: '2026-08-01',
    target: 4000,
    starter_target: 1000,
    starter_met: true,
    reason: '',
    entities: {},
    gaps: [],
    note: null,
    ...over,
  }
}

function renderSheet(s: Signal) {
  return render(
    <SignalBindingSheet budgetId="b1" concept={concept} signal={s} onClose={() => {}} />
  )
}

beforeEach(async () => {
  // GuideDialog pushes a history entry per mount; drain so a stale pop cannot
  // close the next test's dialog.
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  mutateAsync.mockReset().mockResolvedValue({})
})

describe('SignalBindingSheet', () => {
  it('saves a served amount it was reopened with', async () => {
    renderSheet(signal())
    expect(screen.getByLabelText('Amount (optional)')).toHaveValue('1250')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'manual', external: true, external_amount: 1250 })
    )
  })

  it('reads a typed amount the way every money input does', async () => {
    renderSheet(signal({ external_value: null }))
    await userEvent.type(screen.getByLabelText('Amount (optional)'), '1,250.50')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ external_amount: 1250.5 }))
  })

  it('sends no amount for a blank one — "I have this covered" is a whole answer', async () => {
    renderSheet(signal({ external_value: null }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ external_amount: null }))
  })

  it('says an unreadable amount did not parse, and sends nothing', async () => {
    renderSheet(signal({ external_value: null }))
    await userEvent.type(screen.getByLabelText('Amount (optional)'), 'most of it')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByRole('alert')).toHaveTextContent('That amount did not parse')
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it("don't-track still saves for someone who had declared an amount", async () => {
    renderSheet(signal())
    await userEvent.click(screen.getByRole('button', { name: /track this/ }))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ mode: 'dismissed' }))
  })

  it("an unreadable amount does not block don't-track, which records no amount", async () => {
    renderSheet(signal({ external_value: null }))
    await userEvent.type(screen.getByLabelText('Amount (optional)'), 'most of it')
    await userEvent.click(screen.getByRole('button', { name: /track this/ }))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'dismissed', external_amount: null })
    )
  })

  it('keeps Save enabled with nothing chosen, and says what it needs', async () => {
    renderSheet(signal({ external_declared: false, external_value: null, source: 'auto' }))
    const save = screen.getByRole('button', { name: 'Save' })
    expect(save).toBeEnabled()
    expect(save).toHaveClass('dialog-btn', 'dialog-btn--primary')
    await userEvent.click(save)
    expect(screen.getByRole('alert')).toHaveTextContent('Pick what holds it')
    expect(mutateAsync).not.toHaveBeenCalled()
  })
})
