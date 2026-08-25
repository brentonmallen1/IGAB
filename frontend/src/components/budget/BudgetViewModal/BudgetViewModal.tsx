import { useEffect, useMemo, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import {
  useBudgetViews,
  useCreateBudgetView,
  useDeleteBudgetView,
  useUpdateBudgetView,
} from '../../../api/budgetViews'
import { apiErrorMessage } from '../../../api/client'
import { useUIStore } from '../../../stores/uiStore'
import { confirmAsync } from '../../../stores/confirmStore'
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
  // The form's state initializers read the view being edited exactly once, at
  // mount. Mounting before the list has loaded would initialise an empty
  // editor over a real view — and saving that would wipe it.
  if (viewId && !views) return null
  // Keyed so re-pointing the same mounted modal at a different view re-runs
  // the state initializers instead of editing view A's form over view B.
  return (
    <ViewEditor
      key={viewId ?? 'new'}
      budgetId={budgetId}
      viewId={viewId}
      views={views}
      onClose={onClose}
    />
  )
}

function ViewEditor({
  budgetId,
  viewId,
  views,
  onClose,
}: Props & { views: ReturnType<typeof useBudgetViews>['data'] }) {
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
  const [dragging, setDragging] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState<string | null>(null)
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

  // With no groups every category is unassigned; hiding them all would save a
  // view that renders an empty budget page. The toggle is disabled then, and
  // this effective value is what the rows preview and the save send.
  const effectiveHideUnassigned = hideUnassigned && groupNames.length > 0

  function addGroup() {
    const trimmed = newGroup.trim()
    if (!trimmed || groupNames.includes(trimmed)) return
    setGroupNames((g) => [...g, trimmed])
    setNewGroup('')
  }

  /** Returns whether the rename was accepted, so the caller can put the
   *  uncontrolled input back in step when it was not. */
  function renameGroup(from: string, to: string): boolean {
    const trimmed = to.trim()
    if (!trimmed) return false
    if (trimmed === from) return true
    // Refuse a name that already exists rather than silently merging two
    // groups — the server matches groups by name, so a collision would fold
    // one into the other on save.
    if (groupNames.includes(trimmed)) return false
    setGroupNames((g) => g.map((n) => (n === from ? trimmed : n)))
    setAssignment((prev) =>
      Object.fromEntries(
        Object.entries(prev).map(([id, a]) =>
          a.group === from ? [id, { ...a, group: trimmed }] : [id, a]
        )
      )
    )
    return true
  }

  /** Move a group to a position. Order is what the view saves, so this is
   *  the whole feature — no ids, no extra request. */
  function moveGroupTo(name: string, index: number) {
    setGroupNames((current) => {
      const next = current.filter((n) => n !== name)
      next.splice(index, 0, name)
      return next
    })
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
      // Everything in ONE request — placements name their group, so the
      // client never needs ids for groups it is creating in the same breath.
      // Create used to POST the name then PATCH the rest; when the PATCH
      // failed, the committed zero-group view stayed behind.
      const placements = Object.entries(assignment)
        .filter(([, a]) => a.group !== null || a.hidden)
        .map(([category_id, a], i) => ({
          category_id,
          group_name: a.group,
          sort_order: i,
          is_hidden: a.hidden,
        }))

      let id: string
      if (isEdit) {
        id = existing!.id
        await updateView.mutateAsync({
          id,
          name: trimmed,
          hide_unassigned: effectiveHideUnassigned,
          groups: groupNames,
          placements,
        })
      } else {
        id = (
          await createView.mutateAsync({
            name: trimmed,
            hide_unassigned: effectiveHideUnassigned,
            groups: groupNames,
            placements,
          })
        ).id
        setActiveView(id)
      }
      onClose()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Could not save this view'))
    }
  }

  async function handleDelete() {
    if (!existing) return
    const ok = await confirmAsync({
      title: `Delete the view “${existing.name}”?`,
      message: 'Your budget’s own groups and categories are not affected.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    try {
      await deleteView.mutateAsync(existing.id)
      if (activeViewId === existing.id) setActiveView(null)
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not delete this view'))
    }
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
          {/* With no groups, everything is unassigned — hiding the unassigned
              would render the budget page empty. The grid ignores the flag in
              that case (viewGrouping.ts); disabling it here says so up front. */}
          <input
            type="checkbox"
            checked={effectiveHideUnassigned}
            disabled={groupNames.length === 0}
            onChange={(e) => setHideUnassigned(e.target.checked)}
          />
          <span>
            Hide unassigned categories
            <span className="view-editor__toggle-hint">
              {groupNames.length === 0
                ? 'Add a group first — with no groups, every category is unassigned and hiding them would leave this view empty.'
                : hideUnassigned
                  ? 'Anything you don’t place is left out of this view — including categories you add later.'
                  : 'Anything you don’t place shows under Unassigned, so new categories don’t go missing.'}
            </span>
          </span>
        </label>

        <div className="view-editor__section-title">
          Groups in this view
          {groupNames.length > 1 && (
            <span className="view-editor__section-hint"> — drag to reorder</span>
          )}
        </div>
        <div className="view-editor__groups">
          {groupNames.map((g, index) => (
            <span
              key={g}
              className={
                'view-editor__chip' + (dragOver === g ? ' view-editor__chip--drag-over' : '')
              }
              // A view's group order is its array order (the server assigns
              // sort_order from position), so reordering here needs no extra
              // persistence — only a way to say it.
              draggable
              onDragStart={() => setDragging(g)}
              onDragEnd={() => { setDragging(null); setDragOver(null) }}
              onDragOver={(e) => { e.preventDefault(); setDragOver(g) }}
              onDrop={(e) => {
                e.preventDefault()
                if (dragging && dragging !== g) moveGroupTo(dragging, index)
                setDragging(null)
                setDragOver(null)
              }}
            >
              {/* Editable in place: a group name is the whole label the user
                  reads on the budget page, and getting it wrong should not
                  mean deleting the group and reassigning everything in it. */}
              {/* Uncontrolled, so a rejected rename (blank or duplicate)
                  used to leave the typed text sitting in the DOM while state
                  kept the old name — two chips could both read "Need" while
                  the payload still said ["Need", "Want"]. Reset the field
                  explicitly whenever the rename does not take. */}
              <input
                className="view-editor__chip-input"
                defaultValue={g}
                size={Math.max(g.length, 4)}
                onBlur={(e) => {
                  if (!renameGroup(g, e.target.value)) e.target.value = g
                }}
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
            // "Hide unassigned categories" claims every unplaced row. Render
            // that claim on the row itself — a checked, disabled Hide box —
            // or the flag looks like it did nothing.
            const hiddenByFlag = effectiveHideUnassigned && !a?.group && !a?.hidden
            const effectiveHidden = (a?.hidden ?? false) || hiddenByFlag
            return (
              <div
                key={cat.id}
                className={
                  'view-editor__row' + (effectiveHidden ? ' view-editor__row--hidden' : '')
                }
              >
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
                <label
                  className="view-editor__hide"
                  title={
                    hiddenByFlag
                      ? 'Hidden by “Hide unassigned categories” — assign a group to bring it back'
                      : 'Leave this category out of this view'
                  }
                >
                  <input
                    type="checkbox"
                    checked={effectiveHidden}
                    disabled={hiddenByFlag}
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
