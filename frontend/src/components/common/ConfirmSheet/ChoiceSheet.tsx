import { BottomSheet } from '../BottomSheet/BottomSheet'
import type { ChoiceOption } from '../../../stores/confirmStore'
import './ChoiceSheet.css'

interface ChoiceSheetProps {
  open: boolean
  title: string
  message?: string
  options: ChoiceOption[]
  cancelLabel?: string
  onPick: (id: string) => void
  onCancel: () => void
}

/**
 * A confirmation with more than two answers.
 *
 * Sibling to ConfirmSheet rather than a mode of it: a boolean confirm asks
 * "are you sure?", where the shape of the question is already settled. This
 * one asks which of several things should happen, so each option carries its
 * own consequence line — the point is that the outcomes differ, and a user
 * choosing between them needs to see how.
 */
export function ChoiceSheet({
  open,
  title,
  message,
  options,
  cancelLabel = 'Cancel',
  onPick,
  onCancel,
}: ChoiceSheetProps) {
  return (
    <BottomSheet open={open} onClose={onCancel} title={title}>
      <div className="choice-sheet">
        {message && <p className="choice-sheet__message">{message}</p>}
        <div className="choice-sheet__actions">
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              className={`choice-sheet__option press-scale ${
                option.destructive ? 'choice-sheet__option--destructive' : ''
              }`}
              onClick={() => onPick(option.id)}
            >
              <span className="choice-sheet__label">{option.label}</span>
              {option.description && (
                <span className="choice-sheet__description">{option.description}</span>
              )}
            </button>
          ))}
          <button type="button" className="choice-sheet__cancel press-scale" onClick={onCancel}>
            {cancelLabel}
          </button>
        </div>
      </div>
    </BottomSheet>
  )
}
