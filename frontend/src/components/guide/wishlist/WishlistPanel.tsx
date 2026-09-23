import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Heart,
  Plus,
  Settings2,
} from 'lucide-react'
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
  type WishEnvelope,
  type WishlistProject,
} from '../../../api/wishlist'
import { useFormatters } from '../../../hooks/useFormatters'
import { useUndoToast } from '../../../utils/toastUndo'
import { confirmAsync } from '../../../stores/confirmStore'
import { apiErrorMessage } from '../../../api/client'
import { parseDays } from './wishlistCooling'
import { moveItem } from '../../../utils/listOrder'
import { Collapsible } from '../../common/Collapsible/Collapsible'
import { Surface } from '../../common/Surface'
import { WishCard } from './WishCard'
import { WishForm } from './WishForm'
import { ProjectForm } from './ProjectForm'
import { WishlistProjectSection } from './WishlistProjectSection'
import { ReviewDialog } from './ReviewDialog'
import { DeleteWishDialog } from './DeleteWishDialog'
import { SettleWishDialog } from './SettleWishDialog'
import { GuideDialog } from '../GuideDialog'
import { FUN_NOTE, impactLabel, stillWantedLine } from './wishlistCopy'
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
  const { data, isLoading, isError, refetch } = useWishlist(budgetId, enabled)
  const view = useGuideStore((s) => s.wishlistView)
  const sort = useGuideStore((s) => s.wishlistSort)
  const setView = useGuideStore((s) => s.setWishlistView)
  const setSort = useGuideStore((s) => s.setWishlistSort)
  const heroCollapsed = useGuideStore((s) => s.wishlistHeroCollapsed)
  const toggleHero = useGuideStore((s) => s.toggleWishlistHero)
  const collapsedProjects = useGuideStore((s) => s.collapsedWishProjects)
  const toggleProject = useGuideStore((s) => s.toggleWishProject)
  const setCollapsedProjects = useGuideStore((s) => s.setCollapsedWishProjects)
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState<'wish' | 'project' | null>(null)
  const [editing, setEditing] = useState<Wish | null>(null)
  const [editingProject, setEditingProject] = useState<WishlistProject | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [noteOpen, setNoteOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [pendingEnvelope, setPendingEnvelope] = useState<{
    wishName: string
    envelope: WishEnvelope
  } | null>(null)
  /** The wish whose leftover envelope we are asking about. Held by id, not by
   *  value: settling refetches the list, and the dialog must read the row the
   *  server just returned rather than the one that opened it. */
  const [settling, setSettling] = useState<string | null>(null)
  /** Wishes ended inside the review queue, waiting their turn to be asked
   *  about once that dialog is out of the way. */
  const [, setDeferredSettle] = useState<string[]>([])
  const fmt = useFormatters()
  // Every other feature offers the change back before the toast fades; the
  // wishlist quietly did not, so a mis-click on Drop or Delete had no visible
  // way back at all.
  const notify = useUndoToast()
  const [settingsError, setSettingsError] = useState<string | null>(null)
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
  /** Projects whose every wish sits in the hero: their section would
   *  otherwise claim "Nothing on it yet" about a project that is full. */
  const heroProjectIds = useMemo(
    () => new Set(hero.map((w) => w.project_id).filter((id): id is string => id !== null)),
    [hero]
  )
  const { active: activeProjects, complete: completeProjects } = useMemo(
    () => splitProjects(data?.projects ?? []),
    [data]
  )
  const projectsById = useMemo(() => new Map((data?.projects ?? []).map((p) => [p.id, p])), [data])
  // `rest`, not `filtered`: the hero already shows the top priorities above
  // the card, and a wish drawn twice reads as a bug, not emphasis.
  const sections = useMemo(() => groupByProject(rest, activeProjects), [rest, activeProjects])
  const sectionKeys = sections.map((s) => s.project?.id ?? 'loose')
  const allProjectsCollapsed =
    sectionKeys.length > 0 && sectionKeys.every((k) => collapsedProjects.includes(k))
  const due = useMemo(() => (data?.items ?? []).filter((w) => w.review_due), [data])

  if (overview && !enabled) {
    return (
      <section className="guide-wishlist">
        <h2 className="guide-wishlist__title">Wishlist</h2>
        {/* What actually happened, not a reassurance: switching the wishlist
            off returns what its envelopes held to Ready to Assign, and says
            so first (guide/service.py refuses without an explicit release).
            This claimed the money "never moved", which was false whenever
            there was any — two statements about the same money, and the
            comforting one was the wrong one. */}
        <p className="guide-wishlist__lede">
          The wishlist is switched off for this budget. Turn it on in{' '}
          <Link to="/settings">Settings</Link> and its envelopes come back — empty, if you released
          their money to Ready to Assign when you switched it off.
        </p>
      </section>
    )
  }
  if (isError) {
    // `isError` was never read, so a failed fetch rendered an empty
    // paragraph — indistinguishable from an empty wishlist, forever.
    return (
      <section className="guide-wishlist">
        <h2 className="guide-wishlist__title">Wishlist</h2>
        <p className="guide-wishlist__lede">
          The wishlist could not be loaded.{' '}
          <button type="button" className="guide-link-button" onClick={() => void refetch()}>
            Try again
          </button>
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
    const moved = moveItem(ordered, i, i + dir)
    if (moved !== ordered) reorder.mutate([...moved])
  }

  async function deleteWish(wish: Wish) {
    // Delete fired on click with nothing in between. A wish funded from a
    // shared envelope then vanished in silence — no dialog, no toast, no way
    // back that anyone could see. (The envelope dialog below only ever
    // appeared for a wish that owned one, and only after the delete.)
    const ok = await confirmAsync({
      title: `Delete "${wish.name}"?`,
      message:
        'It leaves the list and its history — including whether you talked yourself out of it. ' +
        'Drop it instead to keep that record.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    const result = await remove.mutateAsync(wish.id)
    notify(`${wish.name} deleted`, 'latest')
    if (result.envelope) setPendingEnvelope({ wishName: wish.name, envelope: result.envelope })
  }

  async function deleteProject(project: WishlistProject) {
    // The section simply disappeared and its wishes reappeared under "Other
    // wants" with nothing saying why.
    const count = project.summary.item_count
    const ok = await confirmAsync({
      title: `Delete "${project.name}"?`,
      message: count
        ? `Its ${count === 1 ? 'wish stays' : `${count} wishes stay`} on the list, ungrouped.`
        : 'It has no wishes on it.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    await removeProject.mutateAsync(project.id)
    notify(`${project.name} deleted`, 'latest')
  }

  async function reopen(wish: Wish) {
    await update.mutateAsync({ id: wish.id, status: 'open' })
    // Ending a wish clears its pin (`_apply_status`), and reopening does not
    // put it back — worth saying, since the spotlight is a capped, chosen
    // thing rather than something that follows the wish around.
    notify(
      wish.is_priority
        ? `${wish.name} is back on the list, no longer a top priority`
        : `${wish.name} is back on the list`,
      'latest'
    )
  }

  /** Ending a wish is only half of it: an envelope of its own is left
   *  standing, holding money and still carrying the wish's savings goal. The
   *  server says so in `settlement`; this puts the question in front of the
   *  person while they are still looking at the wish. Dismissing it strands
   *  nothing — the history row goes on asking. */
  async function endWish(wish: Wish, status: 'done' | 'dropped') {
    const ended = await update.mutateAsync({ id: wish.id, status })
    notify(`${wish.name} ${status === 'done' ? 'marked done' : 'dropped'}`, 'latest')
    if (ended.settlement) setSettling(ended.id)
  }

  /** The same ending, from inside the review queue. The prompt waits for the
   *  queue to close rather than opening a dialog on top of one; whichever
   *  wish it was, the history row goes on asking either way. */
  async function endFromReview(wish: Wish, status: 'done' | 'dropped') {
    const ended = await update.mutateAsync({ id: wish.id, status })
    if (ended.settlement) setDeferredSettle((q) => (q.includes(ended.id) ? q : [...q, ended.id]))
  }

  function closeReview() {
    setReviewOpen(false)
    setDeferredSettle((q) => {
      if (q.length > 0) setSettling(q[0])
      return q.slice(1)
    })
  }

  const pinnedCount = data.items.filter((w) => w.is_priority).length
  // Read back from the freshly served list rather than held in state: a
  // settle refetches, and the dialog closing on `settlement: null` is what
  // proves the books are closed. A snapshot taken when it opened could not.
  const settlingWish = settling
    ? ([...data.items, ...data.history].find((w) => w.id === settling) ?? null)
    : null

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
        // A hero floats above the project sections, so it names its project
        // itself — in projects view the section header does it for the rest.
        showProject={hero || view === 'flat'}
        priorityFull={pinnedCount >= data.priority_limit}
        onTogglePriority={() => update.mutate({ id: wish.id, is_priority: !wish.is_priority })}
        onEdit={() => setEditing(wish)}
        onDone={() => void endWish(wish, 'done')}
        onDrop={() => void endWish(wish, 'dropped')}
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
          <h2 className="guide-wishlist__title">
            Wishlist
            <button
              type="button"
              className="guide-icon-button guide-wishlist__note"
              onClick={() => setNoteOpen(true)}
              aria-label={FUN_NOTE.title}
              title={FUN_NOTE.title}
            >
              <Heart size={14} />
            </button>
          </h2>
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
              <button
                type="button"
                className="guide-link-button"
                onClick={() => setReviewOpen(true)}
              >
                Review
              </button>
            </p>
          )}
        </div>
      </header>

      {hero.length > 0 && (
        <section className="guide-wishlist__hero-section">
          <h3 className="guide-wishlist__hero-title">
            <button
              type="button"
              className="guide-wishlist__hero-toggle tap-expand"
              aria-expanded={!heroCollapsed}
              aria-controls="wishlist-hero"
              onClick={toggleHero}
            >
              {heroCollapsed ? (
                <ChevronRight size={14} aria-hidden />
              ) : (
                <ChevronDown size={14} aria-hidden />
              )}
              Top priorities
              <span className="guide-wishlist__hero-count">
                {hero.length}/{data.priority_limit}
              </span>
            </button>
          </h3>
          {!heroCollapsed && (
            <div id="wishlist-hero" className="guide-wishlist__hero">
              {hero.map((w) => card(w, true))}
            </div>
          )}
        </section>
      )}

      <Surface as="div" className="guide-wishlist__card">
        <Surface as="div" variant="chrome" sticky className="guide-wishlist__bar">
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
          <button
            type="button"
            className="guide-checkup__run guide-checkup__run--secondary"
            onClick={() => setAdding('project')}
          >
            Add a project
          </button>
          <button
            type="button"
            className="guide-icon-button"
            onClick={() => setSettingsOpen(true)}
            aria-label="Wishlist settings"
            title="Cooling-off and review defaults"
          >
            <Settings2 size={14} />
          </button>
        </Surface>

        <div className="guide-wishlist__body">
          {data.items.length === 0 ? (
            <p className="guide-wishlist__empty">
              Nothing on the list yet. Add something you want — and give it an envelope, so the
              budget can tell you when.
            </p>
          ) : filtered.length === 0 ? (
            <p className="guide-wishlist__empty">Nothing matches "{query.trim()}".</p>
          ) : rest.length === 0 ? (
            <p className="guide-wishlist__empty">
              Everything on the list sits in your top priorities above.
            </p>
          ) : view === 'flat' ? (
            <div className="guide-wishlist__list">{rest.map((w) => card(w))}</div>
          ) : (
            <div className="guide-wishlist__list">
              {/* At the head of the list, not in the toolbar: it acts on the
                  section carets below it, so it sits where they start. */}
              <button
                type="button"
                className="guide-wishlist__fold-all"
                onClick={() => setCollapsedProjects(allProjectsCollapsed ? [] : sectionKeys)}
              >
                {allProjectsCollapsed ? (
                  <ChevronsUpDown size={14} aria-hidden />
                ) : (
                  <ChevronsDownUp size={14} aria-hidden />
                )}
                {allProjectsCollapsed ? 'Expand all' : 'Collapse all'}
              </button>
              {sections.map((section) => {
                const key = section.project?.id ?? 'loose'
                return (
                  <WishlistProjectSection
                    key={key}
                    project={section.project}
                    count={section.items.length}
                    open={!collapsedProjects.includes(key)}
                    onToggle={() => toggleProject(key)}
                    onEdit={section.project ? () => setEditingProject(section.project) : undefined}
                    onDelete={
                      section.project ? () => void deleteProject(section.project!) : undefined
                    }
                  >
                    {section.items.length ? (
                      section.items.map((w) => card(w))
                    ) : section.project && heroProjectIds.has(section.project.id) ? (
                      <p className="guide-wishlist__empty">
                        Everything on it sits in your top priorities above.
                      </p>
                    ) : (
                      <p className="guide-wishlist__empty">Nothing on it yet.</p>
                    )}
                  </WishlistProjectSection>
                )
              })}
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
                    {fmt.formatMoney(data.drains.total)} moved out of wish envelopes this month.
                  </p>
                  <ul className="wish-drains__list scroll-list">
                    {data.drains.moves.map((m) => (
                      <li key={m.move_id} className="wish-drains__row">
                        <span className="wish-drains__date">
                          {fmt.formatDate(m.date.slice(0, 10))}
                        </span>
                        <span className="wish-drains__amount tabular">
                          {fmt.formatMoney(m.amount)}
                        </span>
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
                  <strong>{w.name}</strong> · {fmt.formatMoney(w.cost)} ·{' '}
                  {w.status === 'done'
                    ? `done ${w.done_at ? fmt.formatDate(w.done_at) : ''}`
                    : `dropped ${w.dropped_at ? fmt.formatDate(w.dropped_at) : ''}`}
                  {/* The prompt that outlives the dialog. Someone who closed
                      the settle question — or ended the wish before this
                      existed — would otherwise have money parked under a name
                      they had already decided against, with nothing anywhere
                      saying so. */}
                  {w.settlement && (
                    <button
                      type="button"
                      className="guide-link-button guide-wishlist__unsettled"
                      onClick={() => setSettling(w.id)}
                    >
                      {w.settlement.available === 0
                        ? `${w.settlement.name} still on your budget`
                        : `${fmt.formatMoney(w.settlement.available)} still in ${w.settlement.name}`}
                    </button>
                  )}
                  <button
                    type="button"
                    className="guide-link-button"
                    aria-label={`Reopen ${w.name}`}
                    onClick={() => void reopen(w)}
                  >
                    Reopen
                  </button>
                </p>
              ))}
            </Collapsible>
          )}
        </div>
      </Surface>

      {adding === 'wish' && (
        <WishForm
          budgetId={budgetId}
          projects={activeProjects}
          defaultCoolingDays={data.settings.cooling_days}
          maxCoolingDays={data.max_cooling_days}
          onClose={() => setAdding(null)}
        />
      )}
      {editing && (
        <WishForm
          budgetId={budgetId}
          wish={editing}
          projects={activeProjects}
          defaultCoolingDays={data.settings.cooling_days}
          maxCoolingDays={data.max_cooling_days}
          onClose={() => setEditing(null)}
        />
      )}
      {settingsOpen && (
        <GuideDialog
          title="Wishlist settings"
          onClose={() => {
            setSettingsError(null)
            setSettingsOpen(false)
          }}
          historyKey="wishlist-settings"
          footer={
            <div className="dialog-actions">
              {settingsError && (
                <span className="dialog-form__error" role="alert">
                  {settingsError}
                </span>
              )}
              <div className="dialog-actions__end">
                <button
                  type="button"
                  className="dialog-btn dialog-btn--secondary"
                  onClick={() => setSettingsOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  form="wishlist-settings-form"
                  className="dialog-btn dialog-btn--primary"
                >
                  Save
                </button>
              </div>
            </div>
          }
        >
          <form
            id="wishlist-settings-form"
            className="guide-wishlist__settings"
            onSubmit={async (e) => {
              e.preventDefault()
              const form = new FormData(e.currentTarget)
              // `Number()` read a cleared box as 0 and anything else as NaN:
              // blanking the cooling-off silently set a zero-day one on every
              // future wish, and a typo sent JSON null. One parser, the served
              // bounds, and a stated reason when it will not do.
              const cooling = parseDays(String(form.get('cooling_days') ?? ''), {
                max: data.max_cooling_days,
                label: 'Cooling-off days',
                blank: 'refuse',
              })
              const review = parseDays(String(form.get('review_after_days') ?? ''), {
                min: data.min_review_days,
                max: data.max_review_days,
                label: '“Still want it?” days',
                blank: 'refuse',
              })
              if (!cooling.ok) return setSettingsError(cooling.error)
              if (!review.ok) return setSettingsError(review.error)
              setSettingsError(null)
              try {
                // Awaited: the dialog used to close first, so a refusal
                // arrived as a toast over a form that was already gone, with
                // the typed values unrecoverable.
                await setSettings.mutateAsync({
                  cooling_days: cooling.days ?? undefined,
                  review_after_days: review.days ?? undefined,
                })
                setSettingsOpen(false)
              } catch (err) {
                setSettingsError(apiErrorMessage(err, 'Could not save settings'))
              }
            }}
          >
            <label className="tool__field">
              <span>Cooling-off for new wishes, days</span>
              <input
                name="cooling_days"
                inputMode="numeric"
                defaultValue={data.settings.cooling_days}
              />
            </label>
            <label className="tool__field">
              <span>Ask "still want it?" after, days</span>
              <input
                name="review_after_days"
                inputMode="numeric"
                defaultValue={data.settings.review_after_days}
              />
            </label>
            {/* They do not behave alike, and saying they do was wrong in a
                way people would only notice as the list changing under them:
                the review cadence is read at serve time for every open wish,
                so shortening it can make wishes due immediately. */}
            <p className="wish-form__hint">
              The cooling-off applies to wishes you add from now on — nothing already on the list
              moves. The “still want it?” gap applies to the whole list, so changing it can bring a
              review forward.
            </p>
          </form>
        </GuideDialog>
      )}
      {adding === 'project' && <ProjectForm budgetId={budgetId} onClose={() => setAdding(null)} />}
      {editingProject && (
        <ProjectForm
          budgetId={budgetId}
          project={editingProject}
          onClose={() => setEditingProject(null)}
        />
      )}
      {reviewOpen && (
        <ReviewDialog
          budgetId={budgetId}
          due={due}
          reviewDays={data.settings.review_after_days}
          onEnd={endFromReview}
          onClose={closeReview}
        />
      )}
      {noteOpen && (
        <GuideDialog
          title={FUN_NOTE.title}
          onClose={() => setNoteOpen(false)}
          historyKey="wishlist-fun"
        >
          {FUN_NOTE.paragraphs.map((text, i) => (
            <p
              key={i}
              className={`dialog__body ${i === FUN_NOTE.paragraphs.length - 1 ? 'dialog__body--muted' : ''}`}
            >
              {text}
            </p>
          ))}
        </GuideDialog>
      )}
      {settlingWish && (
        <SettleWishDialog
          budgetId={budgetId}
          wish={settlingWish}
          onClose={() => setSettling(null)}
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
