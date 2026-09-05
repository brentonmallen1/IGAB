import { useMemo, useState } from 'react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { apiErrorMessage } from '../../../api/client'
import {
  useCreateWish,
  useUpdateWish,
  type FundingMode,
  type Wish,
  type WishlistProject,
} from '../../../api/wishlist'
import { groupedCategorySections } from '../../../utils/categoryPickers'
import { parseAmountInput } from '../../../utils/money'
import { CategoryCombobox } from '../../common/CategoryCombobox/CategoryCombobox'
import { GuideDialog } from '../GuideDialog'

interface Props {
  budgetId: string
  wish?: Wish | null
  projects: WishlistProject[]
  defaultCoolingDays: number
  onClose: () => void
}

/**
 * Add or edit a wish. The funding choice is the point of the form: an
 * envelope of its own in the Wishlist group (the default, made with a
 * savings goal equal to the cost), any existing category, or none yet.
 * An own envelope is chosen when the wish is added; afterwards the budget
 * page owns it, so editing offers only the other two.
 */
export function WishForm({ budgetId, wish, projects, defaultCoolingDays, onClose }: Props) {
  const editing = !!wish
  const [name, setName] = useState(wish?.name ?? '')
  const [cost, setCost] = useState(wish?.cost ?? '')
  const [url, setUrl] = useState(wish?.url ?? '')
  const [notes, setNotes] = useState(wish?.notes ?? '')
  const [projectId, setProjectId] = useState<string>(wish?.project_id ?? '')
  const [coolingDays, setCoolingDays] = useState(String(defaultCoolingDays))
  // Editing works on the stored date, not a day count: days only mean
  // something at creation, when they measure from today.
  const [coolingUntil, setCoolingUntil] = useState(wish?.cooling_until ?? '')
  // Inherited funding seeds 'none': the wish's own stored choice is "no
  // category of its own" — the envelope it shows belongs to the project. The
  // served mode says 'existing' for it, and seeding from that blocked every
  // save behind "Pick the category that funds it" for a category the form
  // deliberately doesn't show.
  const [mode, setMode] = useState<FundingMode>(
    wish
      ? wish.funding.owns_envelope
        ? 'own'
        : wish.funding.inherited
          ? 'none'
          : wish.funding.mode
      : 'own'
  )
  const [categoryId, setCategoryId] = useState<string | null>(
    wish && !wish.funding.inherited ? wish.funding.category_id : null
  )
  const [wantBy, setWantBy] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: categories } = useCategories(budgetId)
  const { data: groups } = useCategoryGroups(budgetId)
  // `is_assignable` — see ProjectForm: a wish names a category to save into.
  const sections = useMemo(
    () =>
      groupedCategorySections(
        (categories ?? []).filter((c) => c.is_assignable),
        groups ?? []
      ),
    [categories, groups]
  )
  const create = useCreateWish(budgetId)
  const update = useUpdateWish(budgetId)
  const pending = create.isPending || update.isPending
  const ownsEnvelope = !!wish?.funding.owns_envelope
  // What "no category of its own" means depends on the project picked right
  // now: with a funded project it follows that envelope, without one it waits.
  const selectedProject = projects.find((p) => p.id === projectId)
  const projectEnvelope = selectedProject?.category_id ? selectedProject.category_name : null

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!name.trim()) return setError('Give it a name')
    const parsedCost = parseAmountInput(cost)
    if (Number.isNaN(parsedCost) || parsedCost < 0) return setError('That cost did not parse')
    if (mode === 'existing' && !categoryId) return setError('Pick the category that funds it')
    const days = coolingDays.trim() === '' ? null : Number(coolingDays)
    if (days !== null && (!Number.isInteger(days) || days < 0 || days > 365)) {
      return setError('Cooling-off days must be a whole number up to 365')
    }
    try {
      if (editing && wish) {
        await update.mutateAsync({
          id: wish.id,
          name: name.trim(),
          cost: String(parsedCost),
          url: url.trim() || null,
          notes: notes.trim() || null,
          project_id: projectId || null,
          cooling_until: coolingUntil || null,
          ...(ownsEnvelope
            ? {}
            : { funding: { mode, category_id: mode === 'existing' ? categoryId : null } }),
        })
      } else {
        await create.mutateAsync({
          name: name.trim(),
          cost: String(parsedCost),
          url: url.trim() || null,
          notes: notes.trim() || null,
          project_id: projectId || null,
          cooling_days: days,
          funding: {
            mode,
            category_id: mode === 'existing' ? categoryId : null,
            want_by: mode === 'own' && wantBy ? wantBy : null,
          },
        })
      }
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save'))
    }
  }

  return (
    <GuideDialog
      title={editing ? 'Edit wish' : 'Add a wish'}
      onClose={onClose}
      historyKey="wishlist-form"
    >
      <form className="dialog__body wish-form" onSubmit={submit}>
        <label className="tool__field">
          <span>What</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="A bike, a trip, a better chair…"
            autoFocus
          />
        </label>
        <div className="tool__grid">
          <label className="tool__field">
            <span>Cost</span>
            <input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
          </label>
          <label className="tool__field">
            <span>Project</span>
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">None</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="wish-form__funding">
          <legend>Where the money lives</legend>
          {ownsEnvelope ? (
            <p className="wish-form__hint">
              Its own envelope, <strong>{wish?.funding.category_name}</strong>, in the Wishlist
              group. Change its goal or move it on the Budget page.
            </p>
          ) : (
            <>
              {!editing && (
                <label className="wish-form__radio">
                  <input
                    type="radio"
                    name="funding"
                    checked={mode === 'own'}
                    onChange={() => setMode('own')}
                  />
                  <span>
                    <strong>An envelope of its own</strong> in the Wishlist group, with a goal of
                    the cost — it shows on the Budget page like any other.
                  </span>
                </label>
              )}
              <label className="wish-form__radio">
                <input
                  type="radio"
                  name="funding"
                  checked={mode === 'existing'}
                  onChange={() => setMode('existing')}
                />
                <span>
                  <strong>An existing category</strong> — several wishes on one envelope queue up by
                  priority.
                </span>
              </label>
              <label className="wish-form__radio">
                <input
                  type="radio"
                  name="funding"
                  checked={mode === 'none'}
                  onChange={() => setMode('none')}
                />
                <span>
                  {projectEnvelope ? (
                    <>
                      <strong>The project&rsquo;s envelope</strong> — funded from {projectEnvelope},
                      alongside the rest of {selectedProject?.name}.
                    </>
                  ) : (
                    <>
                      <strong>Not yet</strong> — decide later.
                    </>
                  )}
                </span>
              </label>
            </>
          )}
          {mode === 'existing' && !ownsEnvelope && (
            <CategoryCombobox
              value={categoryId}
              onChange={setCategoryId}
              groups={sections}
              placeholder="Pick a category"
              sheetTitle="Fund this from"
            />
          )}
          {mode === 'own' && !editing && (
            <label className="tool__field">
              <span>Want it by (optional — gives the envelope a pace)</span>
              <input type="date" value={wantBy} onChange={(e) => setWantBy(e.target.value)} />
            </label>
          )}
        </fieldset>

        {editing ? (
          <label className="tool__field tool__field--inline">
            <span>Cooling off until (blank ends it)</span>
            <input
              type="date"
              value={coolingUntil}
              onChange={(e) => setCoolingUntil(e.target.value)}
            />
          </label>
        ) : (
          <label className="tool__field tool__field--inline">
            <span>Cooling-off, days</span>
            <input
              inputMode="numeric"
              value={coolingDays}
              onChange={(e) => setCoolingDays(e.target.value)}
            />
          </label>
        )}
        <label className="tool__field">
          <span>Link (optional)</span>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
        </label>
        <label className="tool__field">
          <span>Notes (optional)</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </label>

        {error && <p className="tool__error">{error}</p>}
        <div className="wish-form__actions">
          <button type="button" className="guide-link-button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="guide-checkup__run" disabled={pending}>
            {editing ? 'Save' : 'Add to the list'}
          </button>
        </div>
      </form>
    </GuideDialog>
  )
}
