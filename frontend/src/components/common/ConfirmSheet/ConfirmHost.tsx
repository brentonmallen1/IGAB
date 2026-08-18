import { useConfirmStore } from '../../../stores/confirmStore'
import { ConfirmSheet } from './ConfirmSheet'

/**
 * Renders whatever confirmAsync() is currently awaiting. Mounted once at the
 * app root so any code path — including non-React modules under api/ — can
 * raise a themed, keyboard-safe confirmation.
 */
export function ConfirmHost() {
  const request = useConfirmStore((s) => s.request)
  const answer = useConfirmStore((s) => s.answer)

  return (
    <ConfirmSheet
      open={request !== null}
      title={request?.title ?? ''}
      message={request?.message}
      confirmLabel={request?.confirmLabel}
      cancelLabel={request?.cancelLabel}
      destructive={request?.destructive}
      onConfirm={() => answer(true)}
      onCancel={() => answer(false)}
    />
  )
}
