/**
 * The vision-override control must reflect the SERVER, not its first render.
 *
 * The regression: the toggle synced from the server exactly once, so a vision
 * model set later (another device, a completed save) stayed invisible — the
 * toggle read OFF while the worker used the hidden model for every receipt.
 * The "Receipts are scanned by" line is the always-visible ground truth that
 * would have surfaced that incident immediately.
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const updateMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({})))
const settingsState = vi.hoisted(() => ({
  data: undefined as { key: string; value: string }[] | undefined,
}))
const aiStatusState = vi.hoisted(() => ({
  data: undefined as
    | { receipt_model: string; receipt_model_vision?: boolean | null }
    | undefined,
}))

vi.mock('../../api/settings', () => ({
  useSettings: () => settingsState,
  useUpdateSetting: () => ({ mutateAsync: updateMutate, isPending: false }),
}))
vi.mock('../../api/ai', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/ai')>()),
  useAIStatus: () => aiStatusState,
}))

import { AIAdvancedSettings } from './AIAdvancedSettings'

function makeSettings(visionModel: string) {
  return [
    { key: 'ollama_vision_model', value: visionModel },
    { key: 'ollama_options', value: '{}' },
    { key: 'ollama_vision_options', value: '{}' },
    { key: 'ai_vision_timeout_s', value: '300' },
    { key: 'ai_thinking', value: 'auto' },
  ]
}

function visionToggle() {
  return screen.getByRole('checkbox') as HTMLInputElement
}

describe('AIAdvancedSettings vision override sync', () => {
  beforeEach(() => {
    updateMutate.mockClear()
    settingsState.data = undefined
    aiStatusState.data = undefined
  })

  it('shows the override as ON with its value when the server has one', () => {
    settingsState.data = makeSettings('gemma4:31b')
    render(<AIAdvancedSettings />)
    expect(visionToggle().checked).toBe(true)
    expect(screen.getByDisplayValue('gemma4:31b')).toBeInTheDocument()
  })

  it('picks up a server value that changes AFTER the initial load', () => {
    // The frozen-state regression: settings load with no override, then the
    // value appears (saved on another device, refetched here). The old
    // once-only effect never re-ran, leaving the toggle OFF forever.
    settingsState.data = makeSettings('')
    const { rerender } = render(<AIAdvancedSettings />)
    expect(visionToggle().checked).toBe(false)

    settingsState.data = makeSettings('gemma4:31b')
    rerender(<AIAdvancedSettings />)
    expect(visionToggle().checked).toBe(true)
    expect(screen.getByDisplayValue('gemma4:31b')).toBeInTheDocument()
  })

  it('syncs back to OFF when the server value is cleared elsewhere', () => {
    settingsState.data = makeSettings('gemma4:31b')
    const { rerender } = render(<AIAdvancedSettings />)
    expect(visionToggle().checked).toBe(true)

    settingsState.data = makeSettings('')
    rerender(<AIAdvancedSettings />)
    expect(visionToggle().checked).toBe(false)
  })
})

describe('AIAdvancedSettings resolved receipt-model line', () => {
  beforeEach(() => {
    settingsState.data = makeSettings('')
    aiStatusState.data = undefined
  })

  it('names the model that will scan receipts', () => {
    aiStatusState.data = { receipt_model: 'granite4:latest' }
    render(<AIAdvancedSettings />)
    const line = screen.getByTestId('receipt-model-line')
    expect(line).toHaveTextContent('Receipts are scanned by granite4:latest')
  })

  it('warns only when the server says the model lacks vision', () => {
    aiStatusState.data = { receipt_model: 'granite4:latest', receipt_model_vision: false }
    render(<AIAdvancedSettings />)
    expect(screen.getByTestId('receipt-model-line')).toHaveTextContent(
      'this model does not support vision'
    )
  })

  it('does not warn when the server confirms vision', () => {
    aiStatusState.data = { receipt_model: 'gemma4:latest', receipt_model_vision: true }
    render(<AIAdvancedSettings />)
    expect(screen.getByTestId('receipt-model-line')).not.toHaveTextContent('does not support')
  })

  it('does not warn when vision support is unknown (down ≠ misconfigured)', () => {
    // The regression this line had: the verdict came from /api/tags, which
    // omits "vision" for models that have it, so a working gemma4 was
    // labeled unsupported. Absent/null is unknown, never a warning.
    aiStatusState.data = { receipt_model: 'gemma4:latest', receipt_model_vision: null }
    render(<AIAdvancedSettings />)
    expect(screen.getByTestId('receipt-model-line')).not.toHaveTextContent('does not support')

    aiStatusState.data = { receipt_model: 'gemma4:latest' }
    render(<AIAdvancedSettings />)
    expect(screen.getAllByTestId('receipt-model-line')[1]).not.toHaveTextContent(
      'does not support'
    )
  })
})
