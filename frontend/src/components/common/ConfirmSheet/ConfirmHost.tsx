import { useConfirmStore } from '../../../stores/confirmStore'
import { ChoiceSheet } from './ChoiceSheet'
import { ConfirmSheet } from './ConfirmSheet'

/**
 * Renders whatever confirmAsync() or chooseAsync() is currently awaiting.
 * Mounted once at the app root so any code path — including non-React modules
 * under api/ — can raise a themed, keyboard-safe question.
 */
export function ConfirmHost() {
  const request = useConfirmStore((s) => s.request)
  const answer = useConfirmStore((s) => s.answer)
  const choice = useConfirmStore((s) => s.choice)
  const pick = useConfirmStore((s) => s.pick)

  return (
    <>
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
      <ChoiceSheet
        open={choice !== null}
        title={choice?.title ?? ''}
        message={choice?.message}
        options={choice?.options ?? []}
        cancelLabel={choice?.cancelLabel}
        onPick={(id) => pick(id)}
        onCancel={() => pick(null)}
      />
    </>
  )
}
