import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { PERSIST_KEYS } from './persistKeys'
import type { StageId, ToolId } from '../content/roadmap'

export type GuideTab = 'roadmap' | 'checkup' | 'tools' | 'glossary' | 'wishlist'

export interface GuideTabDef {
  id: GuideTab
  label: string
}

export const GUIDE_TABS: GuideTabDef[] = [
  { id: 'roadmap', label: 'Roadmap' },
  { id: 'checkup', label: 'Checkup' },
  { id: 'tools', label: 'Tools' },
  { id: 'glossary', label: 'Glossary' },
  { id: 'wishlist', label: 'Wishlist' },
]

/** How the roadmap is rendered.
 *
 * `journey` walks one stage at a time and is the default — it answers "what
 * next?". `browse` opens everything at once, including both sides of every
 * decision, for reading rather than following. `map` is the chart itself:
 * boxes and arrows, pannable and zoomable, foldable a step at a time. */
export type RoadmapView = 'journey' | 'browse' | 'map'

/** The wishlist as one list sorted, or grouped under its projects. */
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
  wishlistView: WishlistView
  wishlistSort: WishlistSort
  setActiveTab: (tab: GuideTab) => void
  setRoadmapView: (view: RoadmapView) => void
  setActiveTool: (tool: ToolId) => void
  setWishlistView: (view: WishlistView) => void
  setWishlistSort: (sort: WishlistSort) => void
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
      wishlistView: 'flat',
      wishlistSort: 'reach',

      setActiveTab: (tab) => set({ activeTab: tab }),
      setRoadmapView: (view) => set({ roadmapView: view }),
      setActiveTool: (tool) => set({ activeTool: tool }),
      setWishlistView: (view) => set({ wishlistView: view }),
      setWishlistSort: (sort) => set({ wishlistSort: sort }),

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
        wishlistView: s.wishlistView,
        wishlistSort: s.wishlistSort,
      }),
    }
  )
)
