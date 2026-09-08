import { describe, expect, it } from 'vitest'
import { parseFrame } from './chatStream'

describe('parseFrame', () => {
  it('reads a token frame', () => {
    expect(parseFrame('event: token\ndata: {"delta":"hello"}')).toEqual({
      type: 'token',
      delta: 'hello',
    })
  })

  it('reads a start frame with the tools flag', () => {
    expect(parseFrame('event: start\ndata: {"conversation_id":"c1","tools":true}')).toEqual({
      type: 'start',
      conversation_id: 'c1',
      tools: true,
    })
  })

  it('keeps raw and resolved arguments on a tool result', () => {
    // The difference between these two is the whole point of showing them.
    const event = parseFrame(
      'event: tool_result\ndata: {"name":"spending_by_category","arguments":{"months":"3"},"resolved_arguments":{"months":3},"rows":12,"truncated":false}'
    )
    expect(event).toMatchObject({
      type: 'tool_result',
      result: { arguments: { months: '3' }, resolved_arguments: { months: 3 }, rows: 12 },
    })
  })

  it('reads thinking separately from prose', () => {
    // Typed, not a sentinel the client has to regex out of the answer.
    expect(parseFrame('event: thinking\ndata: {"delta":"let me check"}')).toEqual({
      type: 'thinking',
      delta: 'let me check',
    })
  })

  it('reads usage and done', () => {
    expect(parseFrame('event: usage\ndata: {"prompt_tokens":10,"eval_tokens":4}')).toEqual({
      type: 'usage',
      prompt_tokens: 10,
      eval_tokens: 4,
    })
    expect(parseFrame('event: done\ndata: {"message_id":"m1"}')).toEqual({
      type: 'done',
      message_id: 'm1',
    })
  })

  it('reads an error frame', () => {
    expect(parseFrame('event: error\ndata: {"message":"Could not reach Ollama."}')).toEqual({
      type: 'error',
      message: 'Could not reach Ollama.',
    })
  })

  it('ignores an event kind it does not know', () => {
    // A newer server emitting something new is not an error here.
    expect(parseFrame('event: telepathy\ndata: {}')).toBeNull()
  })

  it('ignores a malformed frame rather than throwing mid-stream', () => {
    expect(parseFrame('event: token\ndata: not json')).toBeNull()
    expect(parseFrame('data: {"delta":"no event name"}')).toBeNull()
    expect(parseFrame('')).toBeNull()
  })

  it('tolerates a missing field', () => {
    expect(parseFrame('event: token\ndata: {}')).toEqual({ type: 'token', delta: '' })
  })
})
