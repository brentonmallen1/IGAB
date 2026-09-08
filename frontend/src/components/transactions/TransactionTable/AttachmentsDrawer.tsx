import { useIsMobile } from '../../../hooks/useMediaQuery'
import { AttachmentPanel } from '../../attachments/AttachmentPanel'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { SideDrawer } from '../../common/SideDrawer/SideDrawer'

/**
 * The register's attachments panel, as an overlay that can be closed.
 *
 * It was a fixed side panel with no backdrop, no history entry, no gesture
 * and a 14px close icon that sat under the notch on a phone — the user's
 * report was that once open, there was no way out. On a phone it is a
 * full-height sheet (close button, drag-to-dismiss, Android back); on a
 * desktop a docked drawer beside the register so rows stay selectable.
 */
export function AttachmentsDrawer({
  transactionId,
  onClose,
}: {
  transactionId: string
  onClose: () => void
}) {
  const isMobile = useIsMobile()
  if (isMobile) {
    return (
      <BottomSheet
        open
        onClose={onClose}
        title="Attachments"
        height="full"
        historyKey="attachments"
      >
        <AttachmentPanel transactionId={transactionId} />
      </BottomSheet>
    )
  }
  return (
    <SideDrawer title="Attachments" onClose={onClose} historyKey="attachments">
      <AttachmentPanel transactionId={transactionId} />
    </SideDrawer>
  )
}
