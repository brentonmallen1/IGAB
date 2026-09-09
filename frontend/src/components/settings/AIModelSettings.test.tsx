/**
 * The override controls must reflect the SERVER, not their first render.
 *
 * The regression: the vision toggle synced from the server exactly once, so a
 * vision model set later (another device, a completed save) stayed invisible —
 * the toggle read OFF while the worker used the hidden model for every
 * receipt. The "Receipts are scanned by" line is the always-visible ground
 * truth that would have surfaced that incident immediately. The assistant
 * override is the same control for the same reason.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const updateMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({})))
const settingsState = vi.hoisted(() => ({
  data: undefined as { key: string; value: string }[] | undefined,
}))
const aiStatusState = vi.hoisted(() => ({
  data: undefined as Record<string, unknown> | undefined,
}))
const modelsState = vi.hoisted(() => ({
  data: undefined as
    | { name: string; size: number; capabilities: string[]; context_length: number | null }[]
    | undefined,
  refetch: vi.fn(),
  isFetching: false,
}))

vi.mock('../../api/settings', () => ({
  useSettings: () => settingsState,
  useUpdateSetting: () => ({ mutateAsync: updateMutate, isPending: false }),
}))
vi.mock('../../api/ai', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/ai')>()),
  useAIStatus: () => aiStatusState,
  useOllamaModels: () => modelsState,
}))

import { AIModelSettings } from './AIModelSettings'

function makeSettings(visionModel: string, chatModel = '') {
  return [
    { key: 'ollama_model', value: 'gemma4:latest' },
    { key: 'ollama_vision_model', value: visionModel },
    { key: 'ollama_chat_model', value: chatModel },
  ]
}

function visionToggle() {
  return screen.getByRole('checkbox', { name: /different model for receipts/ }) as HTMLInputElement
}

function assistantToggle() {
  return screen.getByRole('checkbox', {
    name: /different model for the assistant/,
  }) as HTMLInputElement
}

const MODELS = [
  {
    name: 'gemma4:latest',
    size: 9e9,
    capabilities: ['completion', 'vision', 'tools'],
    context_length: 131072,
  },
  {
    name: 'gemma4:31b',
    size: 19e9,
    capabilities: ['completion', 'vision', 'tools'],
    context_length: 131072,
  },
  {
    name: 'moondream:latest',
    size: 1.7e9,
    capabilities: ['completion', 'vision'],
    context_length: 2048,
  },
]

describe('vision override sync', () => {
  beforeEach(() => {
    updateMutate.mockClear()
    settingsState.data = undefined
    aiStatusState.data = undefined
    modelsState.data = MODELS
  })

  it('shows the override as ON with its value when the server has one', () => {
    settingsState.data = makeSettings('gemma4:31b')
    render(<AIModelSettings />)
    expect(visionToggle().checked).toBe(true)
    expect(screen.getByLabelText('Receipt model')).toHaveValue('gemma4:31b')
  })

  it('picks up a server value that changes AFTER the initial load', () => {
    settingsState.data = makeSettings('')
    const { rerender } = render(<AIModelSettings />)
    expect(visionToggle().checked).toBe(false)

    settingsState.data = makeSettings('gemma4:31b')
    rerender(<AIModelSettings />)
    expect(visionToggle().checked).toBe(true)
    expect(screen.getByLabelText('Receipt model')).toHaveValue('gemma4:31b')
  })

  it('syncs back to OFF when the server value is cleared elsewhere', () => {
    settingsState.data = makeSettings('gemma4:31b')
    const { rerender } = render(<AIModelSettings />)
    expect(visionToggle().checked).toBe(true)

    settingsState.data = makeSettings('')
    rerender(<AIModelSettings />)
    expect(visionToggle().checked).toBe(false)
  })

  it('keeps a saved model the server no longer lists', () => {
    modelsState.data = [MODELS[0]]
    settingsState.data = makeSettings('gemma4:31b')
    render(<AIModelSettings />)
    expect(screen.getByLabelText('Receipt model')).toHaveValue('gemma4:31b')
  })
})

describe('assistant override', () => {
  beforeEach(() => {
    updateMutate.mockClear()
    settingsState.data = makeSettings('')
    aiStatusState.data = undefined
    modelsState.data = MODELS
  })

  it('lists models without tool calling but does not let them be chosen', () => {
    settingsState.data = makeSettings('', 'gemma4:31b')
    render(<AIModelSettings />)
    expect(assistantToggle().checked).toBe(true)
    const option = within(screen.getByLabelText('Assistant model')).getByRole('option', {
      name: /moondream/,
    }) as HTMLOptionElement
    expect(option.disabled).toBe(true)
    expect(option.textContent).toContain('no tools')
  })

  it('saves the chosen assistant model', () => {
    settingsState.data = makeSettings('', 'gemma4:latest')
    render(<AIModelSettings />)
    fireEvent.change(screen.getByLabelText('Assistant model'), { target: { value: 'gemma4:31b' } })
    expect(updateMutate).toHaveBeenCalledWith({ key: 'ollama_chat_model', value: 'gemma4:31b' })
  })

  it('turning the override off clears the setting', () => {
    settingsState.data = makeSettings('', 'gemma4:31b')
    render(<AIModelSettings />)
    fireEvent.click(assistantToggle())
    expect(updateMutate).toHaveBeenCalledWith({ key: 'ollama_chat_model', value: '' })
  })
})

describe('resolved model lines', () => {
  beforeEach(() => {
    settingsState.data = makeSettings('')
    aiStatusState.data = undefined
    modelsState.data = MODELS
  })

  const base = { receipt_model: 'granite4:latest', chat_model: 'gemma4:latest' }

  it('names the model that will scan receipts', () => {
    aiStatusState.data = base
    render(<AIModelSettings />)
    expect(screen.getByTestId('receipt-model-line')).toHaveTextContent(
      'Receipts are scanned by granite4:latest'
    )
  })

  it('warns only when the server says the model lacks the capability', () => {
    aiStatusState.data = { ...base, receipt_model_vision: false, chat_model_tools: false }
    render(<AIModelSettings />)
    expect(screen.getByTestId('receipt-model-line')).toHaveTextContent(
      'this model does not support vision'
    )
    expect(screen.getByTestId('assistant-model-line')).toHaveTextContent(
      'this model does not support tools'
    )
  })

  it('does not warn when support is unknown (down ≠ misconfigured)', () => {
    // The regression this line had: the verdict came from /api/tags, which
    // omits "vision" for models that have it, so a working gemma4 was
    // labeled unsupported. Absent/null is unknown, never a warning.
    aiStatusState.data = { ...base, receipt_model_vision: null, chat_model_tools: null }
    render(<AIModelSettings />)
    expect(screen.getByTestId('receipt-model-line')).not.toHaveTextContent('does not support')
    expect(screen.getByTestId('assistant-model-line')).not.toHaveTextContent('does not support')
  })

  it('says how much context the assistant asks for', () => {
    aiStatusState.data = {
      ...base,
      chat_model_tools: true,
      chat_num_ctx: 32768,
      chat_model_context_length: 131072,
    }
    render(<AIModelSettings />)
    expect(screen.getByTestId('assistant-model-line')).toHaveTextContent(
      'asks for 32k of its 128k context'
    )
  })
})
