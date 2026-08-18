/**
 * Reading a failed receipt job's error for the review banner.
 *
 * A scan that failed because no vision model is configured and one that failed
 * because the photo was unreadable produce the identical $0 stub — but only one
 * of them is fixable in Settings, and the user is looking at the stub, not the
 * activity log. These keep that distinction where they'll actually see it.
 */

/** Whether the failure is something the user can fix in Settings. */
export function isConfigFailure(error: string | null | undefined): boolean {
  if (!error) return false
  return /vision|not configured|Settings/i.test(error)
}

/** The job's own error, stripped of the exception-class prefix the worker adds. */
export function scanFailureReason(error: string | null | undefined): string {
  if (!error) return 'Scan failed — enter the details from the image, then approve.'
  return error.replace(/^[A-Za-z]*Error:\s*/, '')
}
