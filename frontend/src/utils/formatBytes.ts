/**
 * A file size, for a person.
 *
 * One implementation because there were three, and they disagreed: the
 * installation backups panel stopped at GB, the per-budget snapshots panel
 * stopped at MB (so a 3 GB archive read as "3072.0 MB"), and the AI panel
 * rounded MB to whole numbers (so two models 400 KB apart both read "31 MB").
 * The same file listed in two panels reported two different sizes.
 *
 * Binary units, as every one of the three used: these are file sizes on disk,
 * and the servers they come from count in KiB.
 */
export function formatBytes(n: number): string {
  if (!Number.isFinite(n)) return '—'
  if (n < 1024) return `${Math.round(n)} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}
