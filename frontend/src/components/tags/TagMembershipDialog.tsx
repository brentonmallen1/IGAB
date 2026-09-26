import { useState } from 'react'
import { useSetTagMembership, useTagMembership } from '../../api/tags'
import { apiErrorMessage } from '../../api/client'
import { Dialog } from '../common/Dialog/Dialog'
import { CategoryMembershipList } from './CategoryMembershipList'
import { initialDraft, isEmptyChange, membershipDiff, type MembershipDraft } from './membershipList'
import './TagMembershipDialog.css'

interface Props {
  budgetId: string
  tagId: string
  /** The tag's name, for the title while the checklist loads. */
  tagName: string
  onClose: () => void
}

/**
 * "Categories tagged {name}" — choosing a tag's categories from the tag's side
 * (Settings → Tags → "N categories"). One Save sends the diff against the
 * checklist as loaded, and the server writes it as one change, so one Cmd+Z
 * undoes it.
 */
export function TagMembershipDialog({ budgetId, tagId, tagName, onClose }: Props) {
  const { data, isLoading, isError, error: loadError } = useTagMembership(budgetId, tagId)
  const save = useSetTagMembership(budgetId, tagId)
  // Null until touched: the draft reads the loaded checklist until the first
  // change, so it is seeded without an effect.
  const [touched, setTouched] = useState<MembershipDraft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const title = `Categories tagged ${data?.tag.name ?? tagName}`
  const formId = `tag-membership-${tagId}`
  const draft = touched ?? (data ? initialDraft(data.categories) : null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!data || !draft) return
    setError(null)
    const change = membershipDiff(data.categories, draft)
    if (isEmptyChange(change)) {
      onClose()
      return
    }
    try {
      await save.mutateAsync(change)
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save those categories'))
    }
  }

  return (
    <Dialog
      title={title}
      onClose={onClose}
      historyKey="tag-membership"
      className="tag-membership"
      footer={
        <div className="dialog-actions">
          {error && (
            <span className="dialog-form__error" role="alert">
              {error}
            </span>
          )}
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              form={formId}
              className="dialog-btn dialog-btn--primary"
              disabled={save.isPending}
            >
              Save
            </button>
          </div>
        </div>
      }
    >
      {isLoading ? (
        <p className="dialog-form__hint">Loading categories…</p>
      ) : isError || !data || !draft ? (
        <p className="dialog-form__error" role="alert">
          {apiErrorMessage(loadError, 'Could not load the categories')}
        </p>
      ) : (
        <form id={formId} className="dialog-form tag-membership__form" onSubmit={submit}>
          <CategoryMembershipList
            rows={data.categories}
            draft={draft}
            onChange={setTouched}
            savingsTag={data.tag.savings_tag}
            label={title}
            fillsSheet
          />
        </form>
      )}
    </Dialog>
  )
}
