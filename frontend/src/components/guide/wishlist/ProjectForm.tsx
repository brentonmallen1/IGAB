import { useMemo, useState } from 'react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { apiErrorMessage } from '../../../api/client'
import { useCreateProject, useUpdateProject, type WishlistProject } from '../../../api/wishlist'
import { groupedCategorySections } from '../../../utils/categoryPickers'
import { CategoryCombobox } from '../../common/CategoryCombobox/CategoryCombobox'
import { GuideDialog } from '../GuideDialog'

interface Props {
  budgetId: string
  project?: WishlistProject | null
  onClose: () => void
}

/** A project: a name, and optionally the envelope its wishes draw on. */
export function ProjectForm({ budgetId, project, onClose }: Props) {
  const editing = !!project
  const [name, setName] = useState(project?.name ?? '')
  const [notes, setNotes] = useState(project?.notes ?? '')
  const [categoryId, setCategoryId] = useState<string | null>(project?.category_id ?? null)
  const [error, setError] = useState<string | null>(null)
  const { data: categories } = useCategories(budgetId)
  const { data: groups } = useCategoryGroups(budgetId)
  const sections = useMemo(
    () => groupedCategorySections(categories ?? [], groups ?? []),
    [categories, groups]
  )
  const create = useCreateProject(budgetId)
  const update = useUpdateProject(budgetId)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!name.trim()) return setError('Give it a name')
    try {
      const body = { name: name.trim(), notes: notes.trim() || null, category_id: categoryId }
      if (editing && project) await update.mutateAsync({ id: project.id, ...body })
      else await create.mutateAsync(body)
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save'))
    }
  }

  return (
    <GuideDialog title={editing ? 'Edit project' : 'Add a project'} onClose={onClose} historyKey="wishlist-project-form">
      <form className="dialog__body wish-form" onSubmit={submit}>
        <label className="tool__field">
          <span>Project</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Japan trip, workshop, nursery…" autoFocus />
        </label>
        <div className="tool__field">
          <span>Funded from (optional — its wishes inherit this)</span>
          <CategoryCombobox
            value={categoryId}
            onChange={setCategoryId}
            groups={sections}
            allowNone
            noneLabel="No envelope yet"
            placeholder="Pick a category"
            sheetTitle="Fund this project from"
          />
        </div>
        <label className="tool__field">
          <span>Notes (optional)</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </label>
        {error && <p className="tool__error">{error}</p>}
        <div className="wish-form__actions">
          <button type="button" className="guide-link-button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="guide-checkup__run" disabled={create.isPending || update.isPending}>
            {editing ? 'Save' : 'Add project'}
          </button>
        </div>
      </form>
    </GuideDialog>
  )
}
