/**
 * The bank-name samples a payee keeps, as a list.
 *
 * One rule, mirrored on the server (`igab.domain.payee_names.dedupe_samples`)
 * because the merge modal previews the list before any round-trip: trimmed,
 * blanks dropped, unique ignoring case with the first spelling kept, in order
 * of first appearance. Never split on anything — a bank name may contain a
 * comma, and splitting on it is how "MALLEN, BRENTON" once became two
 * samples. Both sides run `shared/sample_cases.json`.
 */
export function dedupeSamples(parts: (string | null | undefined)[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const part of parts) {
    if (typeof part !== 'string') continue
    const sample = part.trim()
    const key = sample.toLowerCase()
    if (!sample || seen.has(key)) continue
    seen.add(key)
    out.push(sample)
  }
  return out
}

/** The editor's one-sample-per-line text, as the list it means. */
export function samplesFromLines(text: string): string[] {
  return dedupeSamples(text.split(/\r?\n/))
}
