/**
 * Where the ruler draws its lines. Each position is a CSS expression rather
 * than a measured number: the ruler shows where CSS itself puts things,
 * which is the question being asked.
 */
export const RULER_LINES = [
  {
    id: 'layout-bottom',
    label: 'layout viewport bottom',
    style: { bottom: '0px' },
    tone: 'negative',
  },
  { id: 'app-h', label: 'app-h', style: { top: 'var(--app-h)' }, tone: 'accent' },
  {
    id: 'app-h-plus-safe-top',
    label: 'app-h + safe-top',
    style: { top: 'calc(var(--app-h) + var(--safe-top))' },
    tone: 'warning',
  },
  {
    id: 'safe-bottom',
    label: 'safe-bottom',
    style: { bottom: 'var(--safe-bottom)' },
    tone: 'positive',
  },
  { id: 'safe-top', label: 'safe-top', style: { top: 'var(--safe-top)' }, tone: 'positive' },
] as const
