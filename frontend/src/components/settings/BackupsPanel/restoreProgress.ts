import type { BackupStatus } from '../../../api/backups'

/**
 * What the restore overlay believes, advanced one poll at a time.
 *
 * The overlay used to be a spinner with two exits: `done` reloaded the page,
 * `error` showed the agent's message. There was no third exit. When the
 * restored database would not boot the API (an older dump left newer tables
 * behind; see restore_into_db in scripts/db-backup.sh), every poll failed,
 * every failure was read as "still restarting", and the page promised a
 * reload it was never going to deliver. A person sat in front of "Almost
 * there" until they gave up and refreshed into a wall of 502s.
 *
 * So the state machine is here, pure, with a clock: after the API has been
 * unreachable for RESTORE_GIVE_UP_MS it stops promising and says what to
 * check. The overlay does the polling and the rendering; this decides.
 */

export type RestorePhase = 'restoring' | 'restarting' | 'done' | 'error' | 'stalled'

export interface RestoreProgress {
  phase: RestorePhase
  /** The API confirmed it entered maintenance for our job — after this, an
   *  unreachable API is the restart we asked for, not a network blip. */
  sawMaintenance: boolean
  /** How long the API has gone without answering, in ms. Resets on any reply. */
  unansweredMs: number
  /** The agent's latest progress line, or its error. */
  detail: string | null
}

export type RestorePoll =
  { kind: 'status'; status: BackupStatus } | { kind: 'unreachable'; elapsedMs: number }

export const RESTORE_POLL_MS = 2_000

/**
 * A restart is Alembic plus a uvicorn boot — well under a minute on the
 * slowest home server this has run on. Three minutes of silence is not a slow
 * restart; it is a process that did not come back.
 */
export const RESTORE_GIVE_UP_MS = 3 * 60 * 1000

export const INITIAL_RESTORE_PROGRESS: RestoreProgress = {
  phase: 'restoring',
  sawMaintenance: false,
  unansweredMs: 0,
  detail: null,
}

const TERMINAL: ReadonlySet<RestorePhase> = new Set(['done', 'error', 'stalled'])

export function advanceRestore(prev: RestoreProgress, poll: RestorePoll): RestoreProgress {
  if (TERMINAL.has(prev.phase)) return prev

  if (poll.kind === 'unreachable') {
    const unansweredMs = prev.unansweredMs + poll.elapsedMs
    if (unansweredMs >= RESTORE_GIVE_UP_MS) return { ...prev, unansweredMs, phase: 'stalled' }
    // Only a process we watched shut down counts as "restarting"; before
    // that, a failed poll is a hiccup and the honest word is still the first one.
    const phase = prev.sawMaintenance ? 'restarting' : prev.phase
    return { ...prev, unansweredMs, phase }
  }

  const { status } = poll
  const detail = status.job?.detail ?? prev.detail
  if (status.maintenance) {
    return { phase: 'restoring', sawMaintenance: true, unansweredMs: 0, detail }
  }
  // A fresh process answered: maintenance is in-process state, so a reply
  // without it means the restart happened and status.json holds the outcome.
  const state = status.job?.state
  if (state === 'done') return { ...prev, unansweredMs: 0, detail, phase: 'done' }
  if (state === 'error') return { ...prev, unansweredMs: 0, detail, phase: 'error' }
  return { ...prev, unansweredMs: 0, detail }
}

/** Minutes of silence, for the stalled message — whole minutes, never "0". */
export function unansweredMinutes(progress: RestoreProgress): number {
  return Math.max(1, Math.round(progress.unansweredMs / 60_000))
}
