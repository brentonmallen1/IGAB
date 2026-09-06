/**
 * The restore overlay's exits, including the one it did not have.
 *
 * The incident: the restored database would not boot the API, every poll
 * failed, and the overlay read every failure as "still restarting" — forever.
 * The third exit, `stalled`, is what these pin.
 */
import { describe, expect, it } from 'vitest'
import type { BackupStatus } from '../../../api/backups'
import {
  advanceRestore,
  INITIAL_RESTORE_PROGRESS,
  RESTORE_GIVE_UP_MS,
  RESTORE_POLL_MS,
  unansweredMinutes,
  type RestoreProgress,
} from './restoreProgress'

function status(over: Partial<BackupStatus> = {}, job: Partial<BackupStatus['job']> = {}) {
  return {
    kind: 'status' as const,
    status: {
      agent_online: true,
      maintenance: false,
      queued: false,
      job: {
        id: 'j1',
        action: 'restore',
        state: 'running',
        detail: 'restoring database',
        started_at: null,
        finished_at: null,
        ...job,
      },
      ...over,
    } as BackupStatus,
  }
}

const unreachable = (elapsedMs = RESTORE_POLL_MS) => ({ kind: 'unreachable' as const, elapsedMs })

function afterMaintenance(): RestoreProgress {
  return advanceRestore(INITIAL_RESTORE_PROGRESS, status({ maintenance: true }))
}

describe('the ordinary restore', () => {
  it('shows the agent progress line while the API is in maintenance', () => {
    const p = afterMaintenance()
    expect(p.phase).toBe('restoring')
    expect(p.sawMaintenance).toBe(true)
    expect(p.detail).toBe('restoring database')
  })

  it('calls the API going away a restart, once it has seen maintenance', () => {
    const p = advanceRestore(afterMaintenance(), unreachable())
    expect(p.phase).toBe('restarting')
  })

  it('does not call a blip before maintenance a restart', () => {
    const p = advanceRestore(INITIAL_RESTORE_PROGRESS, unreachable())
    expect(p.phase).toBe('restoring')
  })

  it('finishes when a fresh process answers with the job done', () => {
    let p = advanceRestore(afterMaintenance(), unreachable())
    p = advanceRestore(p, status({ maintenance: false }, { state: 'done' }))
    expect(p.phase).toBe('done')
  })

  it('surfaces the agent error with its message', () => {
    const p = advanceRestore(
      afterMaintenance(),
      status({ maintenance: false }, { state: 'error', detail: 'pg_restore failed: boom' })
    )
    expect(p.phase).toBe('error')
    expect(p.detail).toBe('pg_restore failed: boom')
  })
})

describe('the exit that was missing', () => {
  it('gives up after RESTORE_GIVE_UP_MS of silence', () => {
    let p = afterMaintenance()
    const polls = Math.ceil(RESTORE_GIVE_UP_MS / RESTORE_POLL_MS)
    for (let i = 0; i < polls - 1; i++) {
      p = advanceRestore(p, unreachable())
      expect(p.phase, `poll ${i}`).toBe('restarting')
    }
    p = advanceRestore(p, unreachable())
    expect(p.phase).toBe('stalled')
  })

  it('gives up even if maintenance was never observed', () => {
    // The API can die before the first poll lands; silence is silence.
    let p: RestoreProgress = INITIAL_RESTORE_PROGRESS
    p = advanceRestore(p, unreachable(RESTORE_GIVE_UP_MS))
    expect(p.phase).toBe('stalled')
  })

  it('resets the silence clock on any reply', () => {
    let p = afterMaintenance()
    p = advanceRestore(p, unreachable(RESTORE_GIVE_UP_MS - 1))
    p = advanceRestore(p, status({ maintenance: true }))
    expect(p.unansweredMs).toBe(0)
    p = advanceRestore(p, unreachable(RESTORE_GIVE_UP_MS - 1))
    expect(p.phase).toBe('restarting')
  })

  it('reports whole minutes and never zero', () => {
    expect(unansweredMinutes({ ...INITIAL_RESTORE_PROGRESS, unansweredMs: 20_000 })).toBe(1)
    expect(unansweredMinutes({ ...INITIAL_RESTORE_PROGRESS, unansweredMs: 190_000 })).toBe(3)
  })
})

describe('terminal phases stay put', () => {
  it.each(['done', 'error', 'stalled'] as const)('%s ignores later polls', (phase) => {
    const p: RestoreProgress = { ...INITIAL_RESTORE_PROGRESS, phase }
    expect(advanceRestore(p, status({ maintenance: true }))).toBe(p)
    expect(advanceRestore(p, unreachable())).toBe(p)
  })
})
