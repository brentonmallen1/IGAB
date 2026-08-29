import type { ReactNode } from 'react'
import { Dialog } from '../common/Dialog/Dialog'

/**
 * The shared dialog, carrying the one thing that is the Guide's own.
 *
 * Node cards rendered inside a dialog have no stage ancestor to take
 * `--stage-color` from, so `.guide-dialog` supplies the fallback. Everything
 * else — the desktop/mobile branch, the header, the scroll region — is
 * `common/Dialog`, which is where it belongs now that more than the Guide
 * needs it.
 */
export function GuideDialog({
  title,
  onClose,
  historyKey,
  children,
}: {
  title: string
  onClose: () => void
  historyKey: string
  children: ReactNode
}) {
  return (
    <Dialog title={title} onClose={onClose} historyKey={historyKey} className="guide-dialog">
      {children}
    </Dialog>
  )
}
