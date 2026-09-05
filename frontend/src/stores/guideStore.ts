import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { PERSIST_KEYS } from './persistKeys'
import type { StageId, ToolId } from '../content/roadmap'
import type { GlossaryId } from '../content/glossary'

export type GuideTab = 'roadmap' | 'checkup' | 'tools' | 'glossary'

export interface GuideTabDef {
  id: GuideTab
  label: string
}

export const GUIDE_TABS: GuideTabDef[] = [
  { id: 'roadmap', label: 'Roadmap' },
  { id: 'checkup', label: 'Checkup' },
  { id: 'tools', label: 'Tools' },
  { id: 'glossary', label: 'Glossary' },
]

/** How the roadmap is rendered.
 *
 * `journey` walks one stage at a time and is the default — it answers "what
 * next?". `browse` opens everything at once, including both sides of every
 * decision, for reading rather than following. `map` is the chart itself:
 * boxes and arrows, pannable and zoomable, foldable a step at a time. */
export type RoadmapView = 'journey' | 'browse' | 'map'

/** The wishlist as one list sorted, or grouped under its projects.
 *
 * The wishlist page moved out of the Guide, but its view preferences stay in
 * this store: moving them would orphan what people already have persisted
 * under the guide key, for no gain a user could see. */
export type WishlistView = 'flat' | 'projects'
export type WishlistSort = 'reach' | 'priority' | 'cost' | 'added' | 'name'

interface GuideState {
  activeTab: GuideTab
  roadmapView: RoadmapView
  /** Stage ids the user has opened in journey view. Browse ignores this. */
  expandedStages: StageId[]
  /** Node ids whose "Why this matters" disclosure is open. Deliberately
   *  persisted: someone who wants the depth usually wants it again. */
  expandedDetails: string[]
  /** Answers to decisions the budget cannot infer, keyed by node id. Local
   *  for now; these move to the server with the bindings work so a shared
   *  household budget agrees across devices. */
  answers: Record<string, string>
  /** Which calculator the Tools tab shows. Null means the tab's default. */
  activeTool: ToolId | null
  /** The category plan the planner last had open. Null means the first plan;
   *  a stale id (plan deleted elsewhere) also falls back to the first. */
  activePlanId: string | null
  /** A single glossary term opened from somewhere else — the palette, or a
   *  GlossaryChip. Lifted out of GlossaryPanel's local state so one
   *  definition can have a URL: `/guide?tab=glossary&term=<id>`. Deliberately
   *  NOT persisted; it describes an arrival, not a preference. */
  openGlossaryTerm: GlossaryId | null
  /** The stage the "where you are" cursor last opened for the reader. Journey
   *  opens the current stage once when the cursor moves; after that the
   *  reader's own folding stands until it moves again. */
  positionSeen: StageId | null
  wishlistView: WishlistView
  wishlistSort: WishlistSort
  /** The "Top priorities" strip above the wishlist card, folded away. */
  wishlistHeroCollapsed: boolean
  /** Folded project sections in the wishlist's projects view, by project id
   *  ('loose' is the Other-wants section). A deleted project's id going stale
   *  in here is harmless — nothing renders it. */
  collapsedWishProjects: string[]
  setActiveTab: (tab: GuideTab) => void
  setPositionSeen: (id: StageId | null) => void
  setRoadmapView: (view: RoadmapView) => void
  setActiveTool: (tool: ToolId) => void
  setActivePlanId: (id: string | null) => void
  setOpenGlossaryTerm: (term: GlossaryId | null) => void
  setWishlistView: (view: WishlistView) => void
  setWishlistSort: (sort: WishlistSort) => void
  toggleWishlistHero: () => void
  toggleWishProject: (id: string) => void
  /** Collapse-all / expand-all: the whole set at once. */
  setCollapsedWishProjects: (ids: string[]) => void
  toggleStage: (id: StageId) => void
  openStage: (id: StageId) => void
  toggleDetail: (nodeId: string) => void
  answer: (nodeId: string, answer: string) => void
  clearAnswer: (nodeId: string) => void
}

export const useGuideStore = create<GuideState>()(
  persist(
    (set) => ({
      activeTab: 'roadmap',
      roadmapView: 'journey',
      // The first stage opens on a first visit so the roadmap shows what a
      // stage actually contains. Persisted, so collapsing it sticks.
      expandedStages: ['foundation'],
      expandedDetails: [],
      answers: {},
      activeTool: null,
      activePlanId: null,
      openGlossaryTerm: null,
      positionSeen: null,
      wishlistView: 'flat',
      wishlistSort: 'reach',
      wishlistHeroCollapsed: false,
      collapsedWishProjects: [],

      setActiveTab: (tab) => set({ activeTab: tab }),
      setPositionSeen: (id) => set({ positionSeen: id }),
      setRoadmapView: (view) => set({ roadmapView: view }),
      setActiveTool: (tool) => set({ activeTool: tool }),
      setActivePlanId: (id) => set({ activePlanId: id }),
      setOpenGlossaryTerm: (term) => set({ openGlossaryTerm: term }),
      setWishlistView: (view) => set({ wishlistView: view }),
      setWishlistSort: (sort) => set({ wishlistSort: sort }),
      toggleWishlistHero: () => set((s) => ({ wishlistHeroCollapsed: !s.wishlistHeroCollapsed })),
      toggleWishProject: (id) =>
        set((s) => ({
          collapsedWishProjects: s.collapsedWishProjects.includes(id)
            ? s.collapsedWishProjects.filter((x) => x !== id)
            : [...s.collapsedWishProjects, id],
        })),
      setCollapsedWishProjects: (ids) => set({ collapsedWishProjects: ids }),

      toggleStage: (id) =>
        set((s) => ({
          expandedStages: s.expandedStages.includes(id)
            ? s.expandedStages.filter((x) => x !== id)
            : [...s.expandedStages, id],
        })),

      openStage: (id) =>
        set((s) =>
          s.expandedStages.includes(id) ? s : { expandedStages: [...s.expandedStages, id] }
        ),

      toggleDetail: (nodeId) =>
        set((s) => ({
          expandedDetails: s.expandedDetails.includes(nodeId)
            ? s.expandedDetails.filter((x) => x !== nodeId)
            : [...s.expandedDetails, nodeId],
        })),

      answer: (nodeId, answer) => set((s) => ({ answers: { ...s.answers, [nodeId]: answer } })),

      clearAnswer: (nodeId) =>
        set((s) => {
          const next = { ...s.answers }
          delete next[nodeId]
          return { answers: next }
        }),
    }),
    {
      name: PERSIST_KEYS.guide,
      partialize: (s) => ({
        activeTab: s.activeTab,
        roadmapView: s.roadmapView,
        expandedStages: s.expandedStages,
        expandedDetails: s.expandedDetails,
        answers: s.answers,
        activeTool: s.activeTool,
        activePlanId: s.activePlanId,
        positionSeen: s.positionSeen,
        wishlistView: s.wishlistView,
        wishlistSort: s.wishlistSort,
        wishlistHeroCollapsed: s.wishlistHeroCollapsed,
        collapsedWishProjects: s.collapsedWishProjects,
      }),
    }
  )
)
