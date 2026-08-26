import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Settings2 } from 'lucide-react'
import { useAppStore } from '../../../stores/appStore'
import { useGuideStore, type WishlistSort } from '../../../stores/guideStore'
import { useGuideOverview } from '../../../api/guide'
import {
  useDeleteProject,
  useDeleteWish,
  useReorderWishes,
  useSetWishlistSettings,
  useUpdateWish,
  useWishlist,
  type Wish,
  type WishlistProject,
} from '../../../api/wishlist'
import { useFormatters } from '../../../hooks/useFormatters'
import { Collapsible } from '../../common/Collapsible/Collapsible'
import { Surface } from '../../common/Surface'
import { WishCard } from './WishCard'
import { WishForm } from './WishForm'
import { ProjectForm } from './ProjectForm'
import { WishlistProjectSection } from './WishlistProjectSection'
import { ReviewDialog } from './ReviewDialog'
import { DeleteWishDialog } from './DeleteWishDialog'
import { impactLabel, stillWantedLine } from './wishlistCopy'
import { filterWishes, groupByProject, sortWishes, splitHero, splitProjects } from './wishlistView'
import './Wishlist.css'

const SORTS: { id: WishlistSort; label: string }[] = [
  { id: 'reach', label: 'Soonest' },
  { id: 'priority', label: 'Priority' },
  { id: 'cost', label: 'Cost' },
  { id: 'added', label: 'Newest' },
  { id: 'name', label: 'Name' },
]

/**
 * The Wishlist tab. Not a shopping list — the counterweight to one.
 *
 * A wish is funded by an envelope, so what this tab shows is the budget's
 * own numbers with intent attached: the top priorities with their progress,
 * every wish with its reach, projects with their rollups, the ones due a
 * "still want it?", and what pulled money out of the wishes' envelopes this
 * month. It sorts, filters and groups what is served; it re-derives nothing.
 */
export function WishlistPanel() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: overview } = useGuideOverview(budgetId)
  const enabled = overview ? overview.preferences.wishlist : true
  const { data, isLoading } = useWishlist(budgetId, enabled)
  const view = useGuideStore((s) => s.wishlistView)
  const sort = useGuideStore((s) => s.wishlistSort)
  const setView = useGuideStore((s) => s.setWishlistView)
  const setSort = useGuideStore((s) => s.setWishlistSort)
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState<'wish' | 'project' | null>(null)
  const [editing, setEditing] = useState<Wish | null>(null)
  const [editingProject, setEditingProject] = useState<WishlistProject | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [pendingEnvelope, setPendingEnvelope] = useState<{
    wishName: string
    envelope: { category_id: string; name: string; available: string }
  } | null>(null)
  const fmt = useFormatters()
  const update = useUpdateWish(budgetId ?? '')
  const remove = useDeleteWish(budgetId ?? '')
  const reorder = useReorderWishes(budgetId ?? '')
  const removeProject = useDeleteProject(budgetId ?? '')
  const setSettings = useSetWishlistSettings(budgetId ?? '')

  const filtered = useMemo(
    () => (data ? sortWishes(filterWishes(data.items, data.projects, query), sort) : []),
    [data, query, sort]
  )
  const { hero, rest } = useMemo(
    () => (query ? { hero: [], rest: filtered } : splitHero(filtered)),
    [filtered, query]
  )
  const { active: activeProjects, complete: completeProjects } = useMemo(
    () => splitProjects(data?.projects ?? []),
    [data]
  )
  const projectsById = useMemo(
    () => new Map((data?.projects ?? []).map((p) => [p.id, p])),
    [data]
  )
  const due = useMemo(() => (data?.items ?? []).filter((w) => w.review_due), [data])

  if (overview && !enabled) {
    return (
      <section className="guide-wishlist">
        <h2 className="guide-wishlist__title">Wishlist</h2>
        <p className="guide-wishlist__lede">
          The wishlist is switched off for this budget. Turn it on in{' '}
          <Link to="/settings">Settings</Link> and the Wishlist group in your budget comes back
          with it — any money in those envelopes never moved.
        </p>
      </section>
    )
  }
  if (!budgetId || !data) {
    return <p className="guide-wishlist__lede">{isLoading ? 'Loading…' : ''}</p>
  }

  const stillWanted = stillWantedLine(data.still_wanted)

  function move(wish: Wish, dir: -1 | 1) {
    const ordered = [...data!.items].sort((a, b) => a.priority - b.priority).map((w) => w.id)
    const i = ordered.indexOf(wish.id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= ordered.length) return
    ;[ordered[i], ordered[j]] = [ordered[j], ordered[i]]
    reorder.mutate(ordered)
  }

  async function deleteWish(wish: Wish) {
    const result = await remove.mutateAsync(wish.id)
    if (result.envelope) setPendingEnvelope({ wishName: wish.name, envelope: result.envelope })
  }

  const card = (wish: Wish, hero = false) => {
    const ordered = [...data.items].sort((a, b) => a.priority - b.priority)
    const i = ordered.findIndex((w) => w.id === wish.id)
    const canMove = sort === 'priority' && !query
    return (
      <WishCard
        key={wish.id}
        wish={wish}
        hero={hero}
        project={wish.project_id ? projectsById.get(wish.project_id) : null}
        showProject={view === 'flat'}
        onEdit={() => setEditing(wish)}
        onDone={() => update.mutate({ id: wish.id, status: 'done' })}
        onDrop={() => update.mutate({ id: wish.id, status: 'dropped' })}
        onDelete={() => void deleteWish(wish)}
        onMoveUp={canMove && i > 0 ? () => move(wish, -1) : undefined}
        onMoveDown={canMove && i < ordered.length - 1 ? () => move(wish, 1) : undefined}
      />
    )
  }

  return (
    <section className="guide-wishlist">
      <header className="guide-wishlist__head">
        <div>
          <h2 className="guide-wishlist__title">Wishlist</h2>
          <p className="guide-wishlist__lede">
            Not a shopping list — the counterweight to one. Park a want, give it an envelope, and
            let time and funding decide whether it still matters.
          </p>
        </div>
        <div className="guide-wishlist__status">
          {stillWanted && <p className="guide-wishlist__line">{stillWanted}</p>}
          {due.length > 0 && (
            <p className="guide-wishlist__line">
              {due.length} {due.length === 1 ? 'wish is' : 'wishes are'} due for a review ·{' '}
              <button type="button" className="guide-link-button" onClick={() => setReviewOpen(true)}>
                Review
              </button>
            </p>
          )}
        </div>
      </header>

      {hero.length > 0 && (
        <div className="guide-wishlist__hero" aria-label="Top priorities">
          {hero.map((w) => card(w, true))}
        </div>
      )}

      <Surface variant="chrome" className="guide-wishlist__bar">
        <input
          type="search"
          className="guide-wishlist__search"
          placeholder="Search wishes and projects"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search the wishlist"
        />
        <label className="guide-wishlist__sort">
          <span>Sort</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as WishlistSort)}>
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <div className="guide-viewswitch" role="group" aria-label="Wishlist view">
          {(['flat', 'projects'] as const).map((v) => (
            <button
              key={v}
              type="button"
              className={`guide-viewswitch__button ${view === v ? 'guide-viewswitch__button--active' : ''}`}
              aria-pressed={view === v}
              onClick={() => setView(v)}
            >
              {v === 'flat' ? 'Flat' : 'Projects'}
            </button>
          ))}
        </div>
        <button type="button" className="guide-checkup__run" onClick={() => setAdding('wish')}>
          <Plus size={13} aria-hidden /> Add a wish
        </button>
        <button type="button" className="guide-link-button" onClick={() => setAdding('project')}>
          Add a project
        </button>
        <button
          type="button"
          className="guide-icon-button"
          onClick={() => setSettingsOpen((o) => !o)}
          aria-label="Wishlist settings"
          title="Cooling-off and review defaults"
          aria-expanded={settingsOpen}
        >
          <Settings2 size={14} />
        </button>
      </Surface>

      {settingsOpen && (
        <form
          className="guide-wishlist__settings"
          onSubmit={(e) => {
            e.preventDefault()
            const form = new FormData(e.currentTarget)
            setSettings.mutate({
              cooling_days: Number(form.get('cooling_days')),
              review_after_days: Number(form.get('review_after_days')),
            })
            setSettingsOpen(false)
          }}
        >
          <label className="tool__field tool__field--inline">
            <span>Cooling-off for new wishes, days</span>
            <input name="cooling_days" inputMode="numeric" defaultValue={data.settings.cooling_days} />
          </label>
          <label className="tool__field tool__field--inline">
            <span>Ask "still want it?" after, days</span>
            <input name="review_after_days" inputMode="numeric" defaultValue={data.settings.review_after_days} />
          </label>
          <button type="submit" className="guide-link-button">
            Save
          </button>
        </form>
      )}

      {data.items.length === 0 ? (
        <p className="guide-wishlist__empty">
          Nothing on the list yet. Add something you want — and give it an envelope, so the budget
          can tell you when.
        </p>
      ) : view === 'flat' ? (
        <div className="guide-wishlist__list">{rest.map((w) => card(w))}</div>
      ) : (
        <div className="guide-wishlist__list">
          {groupByProject(filtered, activeProjects).map((section) => (
            <WishlistProjectSection
              key={section.project?.id ?? 'loose'}
              project={section.project}
              count={section.items.length}
              onEdit={section.project ? () => setEditingProject(section.project) : undefined}
              onDelete={section.project ? () => removeProject.mutate(section.project!.id) : undefined}
            >
              {section.items.length ? (
                section.items.map((w) => card(w))
              ) : (
                <p className="guide-wishlist__empty">Nothing on it yet.</p>
              )}
            </WishlistProjectSection>
          ))}
        </div>
      )}

      {data.drains && (
        <section className="wish-drains">
          <h3 className="wish-drains__title">What pulled from your wants</h3>
          {data.drains.moves.length === 0 ? (
            <p className="wish-drains__empty">Nothing left your wants this month.</p>
          ) : (
            <>
              <p className="wish-drains__total">
                {fmt.formatMoney(Number(data.drains.total))} moved out of wish envelopes this month.
              </p>
              <ul className="wish-drains__list">
                {data.drains.moves.map((m) => (
                  <li key={m.move_id} className="wish-drains__row">
                    <span className="wish-drains__date">{fmt.formatDate(m.date.slice(0, 10))}</span>
                    <span className="wish-drains__amount tabular">{fmt.formatMoney(Number(m.amount))}</span>
                    <span className="wish-drains__path">
                      {m.from_name} → {m.to_name}
                    </span>
                    {m.affected.map((a) => (
                      <span key={a.item_id} className="wish-drains__impact">
                        {a.name}: {impactLabel(a.months_further) ?? 'no pace to measure by'}
                      </span>
                    ))}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {(data.history.length > 0 || completeProjects.length > 0) && (
        <Collapsible
          title="History"
          count={data.history.length + completeProjects.length}
          isOpen={historyOpen}
          onToggle={() => setHistoryOpen((o) => !o)}
          className="guide-wishlist__history"
        >
          {completeProjects.map((p) => (
            <p key={p.id} className="guide-wishlist__history-row">
              <strong>{p.name}</strong> — complete
            </p>
          ))}
          {data.history.map((w) => (
            <p key={w.id} className="guide-wishlist__history-row">
              <strong>{w.name}</strong> · {fmt.formatMoney(Number(w.cost))} ·{' '}
              {w.status === 'done' ? `done ${w.done_at ? fmt.formatDate(w.done_at) : ''}` : 'dropped'}
              <button
                type="button"
                className="guide-link-button"
                onClick={() => update.mutate({ id: w.id, status: 'open' })}
              >
                Reopen
              </button>
            </p>
          ))}
        </Collapsible>
      )}

      {adding === 'wish' && (
        <WishForm
          budgetId={budgetId}
          projects={activeProjects}
          defaultCoolingDays={data.settings.cooling_days}
          onClose={() => setAdding(null)}
        />
      )}
      {editing && (
        <WishForm
          budgetId={budgetId}
          wish={editing}
          projects={activeProjects}
          defaultCoolingDays={data.settings.cooling_days}
          onClose={() => setEditing(null)}
        />
      )}
      {adding === 'project' && <ProjectForm budgetId={budgetId} onClose={() => setAdding(null)} />}
      {editingProject && (
        <ProjectForm budgetId={budgetId} project={editingProject} onClose={() => setEditingProject(null)} />
      )}
      {reviewOpen && (
        <ReviewDialog
          budgetId={budgetId}
          due={due}
          reviewDays={data.settings.review_after_days}
          onClose={() => setReviewOpen(false)}
        />
      )}
      {pendingEnvelope && (
        <DeleteWishDialog
          budgetId={budgetId}
          wishName={pendingEnvelope.wishName}
          envelope={pendingEnvelope.envelope}
          onClose={() => setPendingEnvelope(null)}
        />
      )}
    </section>
  )
}
