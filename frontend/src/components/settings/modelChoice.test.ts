import { describe, expect, it } from 'vitest'
import {
  autoWindowLabel,
  canDo,
  contextChoices,
  formatTokens,
  modelOptions,
  sharedContextChoices,
  windowNote,
} from './modelChoice'
import type { OllamaModel } from '../../api/ai'

const withTools: OllamaModel = {
  name: 'qwen3:8b',
  size: 5_000_000_000,
  capabilities: ['completion', 'tools'],
  context_length: 40_960,
}
const noTools: OllamaModel = {
  name: 'moondream:latest',
  size: 1_700_000_000,
  capabilities: ['completion', 'vision'],
  context_length: 2_048,
}
const unknown: OllamaModel = { name: 'old:latest', size: 0, capabilities: [], context_length: null }

describe('canDo', () => {
  it('trusts the server when it says a capability is present or absent', () => {
    expect(canDo(withTools, 'tools')).toBe(true)
    expect(canDo(noTools, 'tools')).toBe(false)
  })

  it('treats no reported capabilities as unknown, not none', () => {
    expect(canDo(unknown, 'tools')).toBe(true)
    expect(canDo(unknown, 'vision')).toBe(true)
  })

  it('any model will do when the job needs nothing special', () => {
    expect(canDo(noTools, undefined)).toBe(true)
  })
})

describe('modelOptions', () => {
  it('disables models the job cannot use and says why', () => {
    const options = modelOptions([withTools, noTools], '', 'tools')
    expect(options.find((o) => o.value === 'moondream:latest')).toMatchObject({
      disabled: true,
      label: expect.stringContaining('no tools'),
    })
    expect(options.find((o) => o.value === 'qwen3:8b')?.disabled).toBe(false)
  })

  it('keeps a saved model the server no longer lists', () => {
    const options = modelOptions([withTools], 'gemma4:31b')
    expect(options[0]).toMatchObject({ value: 'gemma4:31b', disabled: false })
    expect(options[0].label).toContain('not on this server')
  })

  it('does not duplicate a saved model that differs only by :latest', () => {
    const options = modelOptions([{ ...withTools, name: 'gemma4:latest' }], 'gemma4')
    expect(options).toHaveLength(1)
  })

  it('offers everything while the list has not loaded', () => {
    expect(modelOptions(undefined, 'gemma4:31b')).toHaveLength(1)
  })
})

describe('contextChoices', () => {
  it('offers nothing above what the model reports', () => {
    expect(contextChoices(40_960)).toEqual([8_192, 16_384, 32_768])
  })

  it('offers every size when the model does not say', () => {
    expect(contextChoices(null)).toHaveLength(5)
  })
})

describe('sharedContextChoices', () => {
  // One setting serves the receipt model and the assistant's model: a size
  // one of them cannot take would be clamped on the server, a setting that lies.
  it('offers only what every model can take', () => {
    expect(sharedContextChoices([16_384, 131_072])).toEqual([8_192, 16_384])
  })

  it('ignores a model that does not say', () => {
    expect(sharedContextChoices([null, 40_960])).toEqual([8_192, 16_384, 32_768])
  })

  it('offers every size when no model says', () => {
    expect(sharedContextChoices([null, undefined])).toHaveLength(5)
  })
})

describe('autoWindowLabel', () => {
  it('names the window when every model resolved to it', () => {
    expect(autoWindowLabel([32_768, 32_768])).toBe('Auto (32k)')
  })

  it('says it is per model when they differ', () => {
    expect(autoWindowLabel([16_384, 32_768])).toBe('Auto (sized for each model)')
  })

  it('names one model when the other is unknown', () => {
    expect(autoWindowLabel([null, 32_768])).toBe('Auto (32k)')
  })

  it('says nothing it does not know', () => {
    expect(autoWindowLabel([null, undefined])).toBe('Auto (sized from the model)')
  })
})

describe('windowNote', () => {
  it('says what a model is given of what it can take', () => {
    expect(windowNote(32_768, 131_072)).toBe('asks for 32k of its 128k context')
  })

  it('says nothing without both numbers', () => {
    expect(windowNote(null, 131_072)).toBeNull()
    expect(windowNote(32_768, null)).toBeNull()
  })
})

describe('formatTokens', () => {
  it('reads round sizes in k', () => {
    expect(formatTokens(131_072)).toBe('128k')
    expect(formatTokens(4_096)).toBe('4k')
  })

  it('leaves odd sizes as numbers', () => {
    expect(formatTokens(40_960)).toBe('40k')
    expect(formatTokens(40_000)).toBe('40,000')
  })
})
