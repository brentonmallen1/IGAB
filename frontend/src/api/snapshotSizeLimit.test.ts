/**
 * The upload limit is one number that two layers both need, and only one of
 * them can be TypeScript.
 *
 * nginx enforces it and answers a bare 413 the SPA never sees the body of;
 * the client checks it first so a person gets a sentence instead. Written
 * twice by necessity — so this reads the nginx template and fails if they
 * drift, which is the mechanism CLAUDE.md asks for in place of a comment
 * asking the next reader to keep them in step.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { MAX_SNAPSHOT_BYTES, tooLargeMessage } from './budgetSnapshots'

const TEMPLATE = resolve(__dirname, '../../nginx/default.conf.template')

describe('the snapshot upload limit', () => {
  it('matches client_max_body_size in the nginx template', () => {
    const conf = readFileSync(TEMPLATE, 'utf8')
    const match = conf.match(/client_max_body_size\s+(\d+)m\s*;/)
    expect(match, 'no client_max_body_size in the nginx template').not.toBeNull()

    const nginxBytes = Number(match![1]) * 1024 * 1024
    expect(
      MAX_SNAPSHOT_BYTES,
      `MAX_SNAPSHOT_BYTES is ${MAX_SNAPSHOT_BYTES} but nginx allows ${nginxBytes}. ` +
        'A client check that is larger lets nginx answer 413 with nothing the ' +
        'SPA can explain; one that is smaller refuses uploads the server would ' +
        'have taken.'
    ).toBe(nginxBytes)
  })

  it('says nothing about a file that fits', () => {
    expect(tooLargeMessage(1024)).toBeNull()
    expect(tooLargeMessage(MAX_SNAPSHOT_BYTES)).toBeNull()
  })

  it('names both figures when a file is too big', () => {
    const message = tooLargeMessage(MAX_SNAPSHOT_BYTES + 1)
    expect(message).toContain('201 MB')
    expect(message).toContain('200 MB')
  })
})
