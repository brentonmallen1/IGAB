/**
 * The chat's streaming transport.
 *
 * `fetch` rather than axios, because axios buffers a whole response and cannot
 * hand back a reader — and not `EventSource`, which cannot POST or carry an
 * Authorization header. This is the one call in the app that bypasses the axios
 * instance, so it borrows `refreshAccessToken` rather than growing a second
 * answer to "how do we authenticate": without that, a chat opened after the
 * access token expired would fail with a bare 401 while every other request
 * quietly recovered.
 */

import { API_BASE_URL, refreshAccessToken } from './client'
import type { PageContext } from '../components/ai/chat/pageContext'

export interface ToolCallEvent {
  name: string
  /** What the model asked for, before any coercion. */
  arguments: Record<string, unknown>
  /** What actually ran. The gap between the two is where a small model errs. */
  resolved_arguments?: Record<string, unknown> | null
  delegates_to?: string | null
  rows?: number | null
  truncated?: boolean
  duration_ms?: number | null
  error?: string | null
}

export type ChatStreamEvent =
  | { type: 'start'; conversation_id: string; tools: boolean }
  | { type: 'thinking'; delta: string }
  | { type: 'token'; delta: string }
  | { type: 'tool_call'; name: string; arguments: Record<string, unknown> }
  | { type: 'tool_result'; result: ToolCallEvent }
  | { type: 'usage'; prompt_tokens: number | null; eval_tokens: number | null }
  | { type: 'error'; message: string }
  | { type: 'done'; message_id: string | null }

export interface ChatStreamRequest {
  budgetId: string
  message: string
  conversationId?: string | null
  pageContext?: PageContext | null
  clientToday: string
  signal?: AbortSignal
}

/**
 * Send a message and yield events as the server produces them.
 *
 * Retries once on a 401 with a refreshed token, mirroring the axios
 * interceptor. Anything else is thrown for the caller to render.
 */
export async function* streamChat(
  request: ChatStreamRequest
): AsyncGenerator<ChatStreamEvent, void, void> {
  let response = await send(request, localStorage.getItem('access_token'))

  if (response.status === 401) {
    const token = await refreshAccessToken()
    if (token) response = await send(request, token)
  }

  if (!response.ok || !response.body) {
    throw new Error(await errorMessage(response))
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line. A partial frame stays in the
    // buffer until the rest of it arrives.
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = parseFrame(frame)
      if (event) yield event
      boundary = buffer.indexOf('\n\n')
    }
  }
}

function send(request: ChatStreamRequest, token: string | null): Promise<Response> {
  return fetch(`${API_BASE_URL}/${request.budgetId}/ai/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message: request.message,
      conversation_id: request.conversationId ?? null,
      page_context: request.pageContext ?? null,
      client_today: request.clientToday,
    }),
    signal: request.signal,
  })
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // A non-JSON error body is not worth a second failure.
  }
  return `The chat could not start (${response.status}).`
}

/**
 * Per-event parsers, keyed by event name.
 *
 * A table rather than a switch: each entry is independently readable, and an
 * event kind this client does not know about falls out as `undefined` rather
 * than needing a default branch. A newer server emitting something new is not
 * an error.
 */
const PARSERS: Record<string, (d: Record<string, unknown>) => ChatStreamEvent> = {
  start: (d) => ({
    type: 'start',
    conversation_id: String(d.conversation_id ?? ''),
    tools: Boolean(d.tools),
  }),
  thinking: (d) => ({ type: 'thinking', delta: String(d.delta ?? '') }),
  token: (d) => ({ type: 'token', delta: String(d.delta ?? '') }),
  tool_call: (d) => ({
    type: 'tool_call',
    name: String(d.name ?? ''),
    arguments: (d.arguments as Record<string, unknown>) ?? {},
  }),
  tool_result: (d) => ({ type: 'tool_result', result: d as unknown as ToolCallEvent }),
  usage: (d) => ({
    type: 'usage',
    prompt_tokens: (d.prompt_tokens as number | null) ?? null,
    eval_tokens: (d.eval_tokens as number | null) ?? null,
  }),
  error: (d) => ({ type: 'error', message: String(d.message ?? 'Something went wrong.') }),
  done: (d) => ({ type: 'done', message_id: (d.message_id as string | null) ?? null }),
}

/** One `event:`/`data:` frame into a typed event, or null if unrecognised. */
export function parseFrame(frame: string): ChatStreamEvent | null {
  let name = ''
  let raw = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event: ')) name = line.slice(7).trim()
    else if (line.startsWith('data: ')) raw = line.slice(6)
  }
  const parse = PARSERS[name]
  if (!parse || !raw) return null

  try {
    return parse(JSON.parse(raw))
  } catch {
    // A malformed frame must not end the stream.
    return null
  }
}
