/**
 * crypto.randomUUID exists only in secure contexts. A phone browsing the dev
 * server over plain-HTTP LAN (http://<mac-ip>:5173) doesn't get one, and the
 * missing function crashed any render that called it — tapping a transaction
 * blanked the whole app. getRandomValues IS available everywhere, so fall
 * back to assembling a spec-compliant v4 from it. These ids are client-side
 * React keys and draft handles, not security tokens.
 */
export function randomUUID(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40 // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80 // variant 10xx
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'))
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10).join(''),
  ].join('-')
}
