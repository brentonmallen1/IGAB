import { describe, expect, it, vi, beforeEach } from 'vitest'
import { conflictMessage, fetchChangeHead, performUndo } from './changes'
import { ROOT } from './queryKeys'

const api = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }))
vi.mock('./client', () => ({ apiClient: api }))

const qc = { invalidateQueries: vi.fn(), refetchQueries: vi.fn() } as never

describe('performUndo', () => {
  beforeEach(() => {
    api.post.mockReset()
    api.post.mockResolvedValue({ data: { undone_change_ids: ['c1'], skipped_change_ids: [] } })
    ;(qc as { invalidateQueries: ReturnType<typeof vi.fn> }).invalidateQueries.mockClear()
  })

  it.each([
    ['latest', '/b1/changes/undo'],
    [{ batch: 'bt-1' }, '/b1/changes/batch/bt-1/undo'],
    [{ change: 'ch-1' }, '/b1/changes/ch-1/undo'],
  ] as const)('addresses %j at %s', async (target, path) => {
    await performUndo(qc, 'b1', target)
    expect(api.post).toHaveBeenCalledExactlyOnceWith(path)
  })

  it('invalidates the change log and the money surfaces once', async () => {
    await performUndo(qc, 'b1', 'latest')
    const calls = (qc as { invalidateQueries: ReturnType<typeof vi.fn> }).invalidateQueries.mock
      .calls
    expect(calls).toContainEqual([{ queryKey: [ROOT.changes, 'b1'] }])
    expect(calls).toContainEqual([{ queryKey: [ROOT.transactions] }])
  })
})

describe('conflictMessage', () => {
  it('reads a structured 409 detail', () => {
    expect(conflictMessage({ response: { data: { detail: { message: 'Newer changes' } } } })).toBe(
      'Newer changes'
    )
  })
  it('reads a string detail', () => {
    expect(conflictMessage({ response: { data: { detail: 'Nothing to undo' } } })).toBe(
      'Nothing to undo'
    )
  })
  it('is undefined for anything else', () => {
    expect(conflictMessage(new Error('boom'))).toBeUndefined()
  })
})

describe('fetchChangeHead', () => {
  it('asks for one row and returns its seq', async () => {
    api.get.mockResolvedValue({ data: { changes: [{ seq: 41 }], total: 9, names: {} } })
    expect(await fetchChangeHead('b1')).toBe(41)
    expect(api.get).toHaveBeenCalledWith('/b1/changes', { params: { limit: 1, offset: 0 } })
  })
  it('is 0 for an empty log', async () => {
    api.get.mockResolvedValue({ data: { changes: [], total: 0, names: {} } })
    expect(await fetchChangeHead('b1')).toBe(0)
  })
})
