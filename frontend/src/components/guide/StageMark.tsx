import { Check, MinusCircle } from 'lucide-react'
import type { StageId } from '../../content/roadmap'
import { useSetGuideStep } from '../../api/guide'

/**
 * "Mark done" / "Skip" on a roadmap stage, and the quiet line that replaces
 * them once pressed.
 *
 * The mark is the blunt instrument for what detection cannot see — weighing a
 * Roth against a Traditional is judgement, not arithmetic. It wins: a marked
 * stage shows the mark and never a health marker, however the numbers read.
 * Undo returns the stage to undecided. Rendered as a sibling of the stage's
 * header button, never inside it — nested buttons are not HTML.
 */
export function StageMark({
  budgetId,
  stageId,
  mark,
  showControls = true,
}: {
  budgetId: string
  stageId: StageId
  mark?: 'done' | 'skipped'
  /** Offer the buttons. A collapsed row shows only an existing mark. */
  showControls?: boolean
}) {
  const setStep = useSetGuideStep(budgetId)
  const save = (state: 'done' | 'skipped' | null) => setStep.mutate({ stageId, state })
  const error = setStep.isError && <span className="guide-stage__mark-error">Couldn’t save</span>

  if (mark) {
    return (
      <div className="guide-stage__mark">
        <span className={`guide-stage__marked guide-stage__marked--${mark}`}>
          {mark === 'done' ? <Check size={12} aria-hidden /> : <MinusCircle size={12} aria-hidden />}
          {mark === 'done' ? 'you marked this done' : 'you skipped this'}
        </span>
        <button
          type="button"
          className="guide-link-button"
          onClick={() => save(null)}
          disabled={setStep.isPending}
        >
          Undo
        </button>
        {error}
      </div>
    )
  }

  if (!showControls) return null

  return (
    <div className="guide-stage__mark guide-stage__mark--quiet">
      <button
        type="button"
        className="guide-link-button"
        onClick={() => save('done')}
        disabled={setStep.isPending}
      >
        Mark done
      </button>
      <span aria-hidden>·</span>
      <button
        type="button"
        className="guide-link-button"
        onClick={() => save('skipped')}
        disabled={setStep.isPending}
      >
        Skip
      </button>
      {error}
    </div>
  )
}
