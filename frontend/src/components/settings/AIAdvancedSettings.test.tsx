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
  data: undefined as { receipt_model: string } | undefined,
}))
const modelsState = vi.hoisted(() => ({
  data: undefined as { name: string; size: number; capabilities: string[] }[] | undefined,
}))

vi.mock('../../api/settings', () => ({
  useSettings: () => settingsState,
  useUpdateSetting: () => ({ mutateAsync: updateMutate, isPending: false }),
}))
vi.mock('../../api/ai', async (importOriginal) => ({
  // Keep the real sameOllamaModel — the ":latest" normalization is part of
  // what the warning logic under test relies on.
  ...(await importOriginal<typeof import('../../api/ai')>()),
  useAIStatus: () => aiStatusState,
  useOllamaModels: () => modelsState,
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
    modelsState.data = undefined
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
    modelsState.data = undefined
  })

  it('names the model that will scan receipts', () => {
    aiStatusState.data = { receipt_model: 'granite4:latest' }
    render(<AIAdvancedSettings />)
    const line = screen.getByTestId('receipt-model-line')
    expect(line).toHaveTextContent('Receipts are scanned by granite4:latest')
  })

  it('warns when Ollama knows the model and it lacks vision', () => {
    aiStatusState.data = { receipt_model: 'granite4:latest' }
    modelsState.data = [{ name: 'granite4:latest', size: 1, capabilities: ['completion'] }]
    render(<AIAdvancedSettings />)
    expect(screen.getByTestId('receipt-model-line')).toHaveTextContent(
      'this model does not support vision'
    )
  })

  it('does not warn when the model advertises vision', () => {
    aiStatusState.data = { receipt_model: 'gemma4:31b' }
    modelsState.data = [{ name: 'gemma4:31b', size: 1, capabilities: ['completion', 'vision'] }]
    render(<AIAdvancedSettings />)
    expect(screen.getByTestId('receipt-model-line')).not.toHaveTextContent('does not support')
  })

  it('does not warn when the model is unknown to Ollama (down ≠ misconfigured)', () => {
    aiStatusState.data = { receipt_model: 'gemma4:31b' }
    modelsState.data = []
    render(<AIAdvancedSettings />)
    expect(screen.getByTestId('receipt-model-line')).not.toHaveTextContent('does not support')
  })

  it('matches an untagged setting against the tagged tile name', () => {
    // env-seeded "granite4" vs /api/tags "granite4:latest" — same model.
    aiStatusState.data = { receipt_model: 'granite4' }
    modelsState.data = [{ name: 'granite4:latest', size: 1, capabilities: ['completion'] }]
    render(<AIAdvancedSettings />)
    expect(screen.getByTestId('receipt-model-line')).toHaveTextContent(
      'this model does not support vision'
    )
  })
})
