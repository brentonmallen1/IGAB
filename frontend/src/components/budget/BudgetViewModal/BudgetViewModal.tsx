import { useEffect, useMemo, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import {
  useBudgetViews,
  useCreateBudgetView,
  useDeleteBudgetView,
  useUpdateBudgetView,
} from '../../../api/budgetViews'
import { useUIStore } from '../../../stores/uiStore'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import './BudgetViewModal.css'

interface Props {
  budgetId: string
  viewId: string | null
  onClose: () => void
}

/** Where a category sits while the user is editing. `group` is a group NAME,
 *  not an id: groups are created and renamed in the same dialog, so names are
 *  the only stable handle until the save round-trips. */
type Assignment = Record<string, { group: string | null; hidden: boolean }>

export function BudgetViewModal({ budgetId, viewId, onClose }: Props) {
  const { data: views } = useBudgetViews(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId, true)
  const { data: categories = [] } = useCategories(budgetId, true)
  const createView = useCreateBudgetView(budgetId)
  const updateView = useUpdateBudgetView(budgetId)
  const deleteView = useDeleteBudgetView(budgetId)
  const setActiveView = useUIStore((s) => s.setActiveView)
  const activeViewId = useUIStore((s) => s.activeViewId)

  const existing = views?.find((v) => v.id === viewId) ?? null
  const isEdit = !!existing

  const [name, setName] = useState(existing?.name ?? '')
  const [groupNames, setGroupNames] = useState<string[]>(
    () => existing?.groups.map((g) => g.name) ?? []
  )
  const [newGroup, setNewGroup] = useState('')
  const [hideUnassigned, setHideUnassigned] = useState(existing?.hide_unassigned ?? false)
  const [assignment, setAssignment] = useState<Assignment>(() => {
    if (!existing) return {}
    const nameById = new Map(existing.groups.map((g) => [g.id, g.name]))
    return Object.fromEntries(
      existing.placements.map((p) => [
        p.category_id,
        { group: p.group_id ? (nameById.get(p.group_id) ?? null) : null, hidden: p.is_hidden },
      ])
    )
  })
  const [error, setError] = useState<string | null>(null)

  const nameRef = useRef<HTMLInputElement>(null)
  const trapRef = useFocusTrap<HTMLFormElement>(onClose)
  useEffect(() => { nameRef.current?.focus() }, [])

  const groupNameById = useMemo(
    () => new Map(groups.map((g) => [g.id, g.name])),
    [groups]
  )

  function addGroup() {
    const trimmed = newGroup.trim()
    if (!trimmed || groupNames.includes(trimmed)) return
    setGroupNames((g) => [...g, trimmed])
    setNewGroup('')
  }

  function renameGroup(from: string, to: string) {
    const trimmed = to.trim()
    if (!trimmed || trimmed === from) return
    // Refuse a name that already exists rather than silently merging two
    // groups — the server matches groups by name, so a collision would fold
    // one into the other on save.
    if (groupNames.includes(trimmed)) return
    setGroupNames((g) => g.map((n) => (n === from ? trimmed : n)))
    setAssignment((prev) =>
      Object.fromEntries(
        Object.entries(prev).map(([id, a]) =>
          a.group === from ? [id, { ...a, group: trimmed }] : [id, a]
        )
      )
    )
  }

  function removeGroup(target: string) {
    setGroupNames((g) => g.filter((n) => n !== target))
    // Categories in a removed group fall back to Unassigned rather than out of
    // the view — the same thing the server does when a group is deleted.
    setAssignment((prev) =>
      Object.fromEntries(
        Object.entries(prev).map(([id, a]) =>
          a.group === target ? [id, { ...a, group: null }] : [id, a]
        )
      )
    )
  }

  function assign(categoryId: string, group: string | null) {
    setAssignment((prev) => ({
      ...prev,
      [categoryId]: { group, hidden: prev[categoryId]?.hidden ?? false },
    }))
  }

  function toggleHidden(categoryId: string) {
    setAssignment((prev) => ({
      ...prev,
      [categoryId]: {
        group: prev[categoryId]?.group ?? null,
        hidden: !prev[categoryId]?.hidden,
      },
    }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    setError(null)

    try {
      const id = isEdit
        ? existing!.id
        : (await createView.mutateAsync({ name: trimmed, hide_unassigned: hideUnassigned })).id

      // Groups and placements in one request: placements name their group, so
      // the client never needs ids for groups it is creating in the same
      // breath — and a failure can't leave the view renamed but unplaced.
      const placements = Object.entries(assignment)
        .filter(([, a]) => a.group !== null || a.hidden)
        .map(([category_id, a], i) => ({
          category_id,
          group_name: a.group,
          sort_order: i,
          is_hidden: a.hidden,
        }))

      await updateView.mutateAsync({
        id,
        ...(isEdit ? { name: trimmed } : {}),
        hide_unassigned: hideUnassigned,
        groups: groupNames,
        placements,
      })

      if (!isEdit) setActiveView(id)
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Could not save this view')
    }
  }

  async function handleDelete() {
    if (!existing) return
    await deleteView.mutateAsync(existing.id)
    if (activeViewId === existing.id) setActiveView(null)
    onClose()
  }

  const isPending = createView.isPending || updateView.isPending

  return (
    <div className="view-editor-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form
        ref={trapRef}
        tabIndex={-1}
        className="view-editor"
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal
        aria-labelledby="view-editor-title"
      >
        <div className="view-editor__header">
          <span id="view-editor-title" className="view-editor__title">
            {isEdit ? 'Edit View' : 'New View'}
          </span>
          <button type="button" className="view-editor__close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        <p className="view-editor__hint">
          A view is a different way to arrange the same categories — group them by
          need and want, or however you think. It doesn’t change your budget’s own
          groups, so you can switch back any time. Anything you don’t place shows
          under <strong>Unassigned</strong>.
        </p>

        <input
          ref={nameRef}
          className="view-editor__input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="View name, e.g. Need / Want / Save"
          maxLength={100}
          required
        />

        <label className="view-editor__toggle">
          <input
            type="checkbox"
            checked={hideUnassigned}
            onChange={(e) => setHideUnassigned(e.target.checked)}
          />
          <span>
            Hide unassigned categories
            <span className="view-editor__toggle-hint">
              {hideUnassigned
                ? 'Anything you don’t place is left out of this view — including categories you add later.'
                : 'Anything you don’t place shows under Unassigned, so new categories don’t go missing.'}
            </span>
          </span>
        </label>

        <div className="view-editor__section-title">Groups in this view</div>
        <div className="view-editor__groups">
          {groupNames.map((g) => (
            <span key={g} className="view-editor__chip">
              {/* Editable in place: a group name is the whole label the user
                  reads on the budget page, and getting it wrong should not
                  mean deleting the group and reassigning everything in it. */}
              <input
                className="view-editor__chip-input"
                defaultValue={g}
                size={Math.max(g.length, 4)}
                onBlur={(e) => renameGroup(g, e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() }
                  if (e.key === 'Escape') { e.currentTarget.value = g; e.currentTarget.blur() }
                }}
                aria-label={`Rename group ${g}`}
                maxLength={100}
              />
              <button
                type="button"
                onClick={() => removeGroup(g)}
                aria-label={`Remove group ${g}`}
                className="view-editor__chip-remove"
              >
                <X size={11} />
              </button>
            </span>
          ))}
          <span className="view-editor__add-group">
            <input
              className="view-editor__input view-editor__input--inline"
              value={newGroup}
              onChange={(e) => setNewGroup(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); addGroup() }
              }}
              placeholder="Add a group…"
              maxLength={100}
            />
            <button type="button" className="view-editor__add-btn" onClick={addGroup}>
              <Plus size={12} />
            </button>
          </span>
        </div>

        <div className="view-editor__section-title">Where each category goes</div>
        <div className="view-editor__categories">
          {categories.map((cat) => {
            const a = assignment[cat.id]
            return (
              <div key={cat.id} className="view-editor__row">
                <span className="view-editor__cat">
                  {cat.name}
                  <span className="view-editor__cat-group">
                    {groupNameById.get(cat.category_group_id)}
                  </span>
                </span>
                <select
                  className="view-editor__select"
                  value={a?.group ?? ''}
                  onChange={(e) => assign(cat.id, e.target.value || null)}
                  disabled={a?.hidden}
                  aria-label={`Group for ${cat.name}`}
                >
                  <option value="">Unassigned</option>
                  {groupNames.map((g) => (
                    <option key={g} value={g}>{g}</option>
                  ))}
                </select>
                <label className="view-editor__hide" title="Leave this category out of this view">
                  <input
                    type="checkbox"
                    checked={a?.hidden ?? false}
                    onChange={() => toggleHidden(cat.id)}
                  />
                  Hide
                </label>
              </div>
            )
          })}
        </div>

        {error && <p className="view-editor__error">{error}</p>}

        <div className="view-editor__footer">
          {isEdit ? (
            <button type="button" className="view-editor__btn view-editor__btn--danger" onClick={handleDelete}>
              Delete
            </button>
          ) : (
            <span />
          )}
          <div className="view-editor__footer-actions">
            <button type="button" className="view-editor__btn" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="view-editor__btn view-editor__btn--primary" disabled={isPending}>
              {isEdit ? 'Save' : 'Create'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
