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
  /* The line that answers the question. With an opaque status bar it should
     sit ON layout-bottom; any daylight between them is the band. There used
     to be an `app-h + safe-top` line beside it, from when the shell had to
     add the top inset back to reach the screen — with the web view starting
     below the status bar it coincides with app-h and says nothing. */
  { id: 'app-h', label: 'app-h', style: { top: 'var(--app-h)' }, tone: 'accent' },
  {
    id: 'safe-bottom',
    label: 'safe-bottom',
    style: { bottom: 'var(--safe-bottom)' },
    tone: 'positive',
  },
  { id: 'safe-top', label: 'safe-top', style: { top: 'var(--safe-top)' }, tone: 'positive' },
] as const
