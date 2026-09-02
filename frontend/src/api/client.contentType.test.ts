/**
 * The apiClient must never force a Content-Type: axios derives it from the
 * body. This is load-bearing for every upload in the app.
 *
 * With a default `Content-Type: application/json` on the instance (which this
 * client shipped with until the snapshot importer hit it), axios does not
 * override the forced type for FormData — it *serializes the FormData as
 * JSON*, turning the File into `{}`. The server then sees a JSON body with no
 * multipart `file` field and answers 422 "Field required". Five call sites
 * carried per-request overrides to dodge this, in two different spellings;
 * the snapshot importer was the sixth site and had none.
 *
 * These tests run real requests through apiClient (interceptors and
 * transformRequest included) into a stub adapter, and assert on what would
 * have gone over the wire.
 */

import { describe, expect, it } from 'vitest'
import type { AxiosRequestConfig, AxiosResponse } from 'axios'
import { apiClient } from './client'

/** Capture the fully transformed request instead of sending it. */
async function outgoing(data: unknown): Promise<AxiosRequestConfig> {
  let captured: AxiosRequestConfig | null = null
  await apiClient.post('/anywhere', data, {
    adapter: (config) => {
      captured = config
      return Promise.resolve({
        data: null,
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      } as AxiosResponse)
    },
  })
  if (!captured) throw new Error('adapter never ran')
  return captured
}

function contentType(config: AxiosRequestConfig): string {
  const value = (config.headers as { getContentType?: () => unknown })?.getContentType?.()
  return typeof value === 'string' ? value : ''
}

describe('apiClient content-type negotiation', () => {
  it('sends FormData as FormData, not serialized to JSON', async () => {
    const form = new FormData()
    form.append('file', new File(['zip bytes'], 'snapshot.igab.zip'))

    const config = await outgoing(form)

    // The forced-JSON failure mode turned this into the string '{"file":{}}'.
    expect(config.data).toBeInstanceOf(FormData)
    expect((config.data as FormData).get('file')).toBeInstanceOf(File)
    expect(contentType(config)).not.toContain('application/json')
  })

  it('still sends plain objects as JSON', async () => {
    const config = await outgoing({ name: 'Groceries' })

    expect(config.data).toBe(JSON.stringify({ name: 'Groceries' }))
    expect(contentType(config)).toContain('application/json')
  })
})
