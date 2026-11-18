import type { AIJob } from '../../../api/aiJobs'

/**
 * Reading a failed receipt job's error for the review banner.
 *
 * A scan that failed because no vision model is configured and one that failed
 * because the photo was unreadable produce the identical $0 stub — but only one
 * of them is fixable in System → AI, and the user is looking at the stub, not
 * the activity log. These keep that distinction where they'll actually see it.
 */

/** Whether the failure is something the user can fix in System → AI. The
 *  server names that page in its message; "Settings" is what it said before
 *  the AI section moved, and a job recorded then still reads the same. */
export function isConfigFailure(error: string | null | undefined): boolean {
  if (!error) return false
  return /vision|not configured|Settings|System/i.test(error)
}

const GENERIC = 'Scan failed — enter the details from the image, then approve.'

/** The job's own error. The server now writes a sentence for people
 *  (`backend/.../ai/failure_text.py`); a job recorded before that carries an
 *  exception name in front ("ReadTimeout: ", "ReplyNotJSON: …"), stripped
 *  here — and a bare "ReadTimeout: " with nothing after it reads as the
 *  general guidance, not as a blank banner. */
export function scanFailureReason(error: string | null | undefined): string {
  const reason = (error ?? '').replace(/^[A-Z][a-z]+(?:[A-Z][A-Za-z]*)+:\s*/, '').trim()
  return reason || GENERIC
}

/** A failure as the page shows it: the headline always, the rest behind
 *  Details (the review banner keeps the next step in view). */
export interface ScanFailure {
  headline: string
  nextStep: string | null
  technical: string | null
  /** The setting that helps, as the screen labels it; the link goes to
   *  System → AI. */
  settings: string | null
}

/** The job's failure in layers. A job recorded before the server wrote
 *  them has one line, which becomes the headline. */
export function jobFailure(job: Pick<AIJob, 'error' | 'result'>): ScanFailure {
  const failure = job.result?.failure
  if (failure) {
    return {
      headline: failure.headline,
      nextStep: failure.next_step || null,
      technical: failure.technical || null,
      settings: failure.settings || null,
    }
  }
  return {
    headline: scanFailureReason(job.error),
    nextStep: null,
    technical: null,
    settings: isConfigFailure(job.error) ? 'System → AI' : null,
  }
}
