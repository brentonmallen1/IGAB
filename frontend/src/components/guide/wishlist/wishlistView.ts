import type { Wish, WishlistProject } from '../../../api/wishlist'
import type { WishlistSort } from '../../../stores/guideStore'

/**
 * Sorting, searching and grouping what the server sent. Presentation only:
 * nothing here re-derives a figure — reach, rollups and counts are served.
 */

/** How many priorities sit above the list with progress bars. */
export const HERO_COUNT = 3

const REACH_ORDER: Record<string, number> = { now: 0, months: 1, no_rate: 2, unlinked: 3 }

function reachKey(w: Wish): [number, number] {
  if (!w.reach) return [9, 0]
  return [REACH_ORDER[w.reach.state] ?? 9, w.reach.months ?? 0]
}

export function sortWishes(items: Wish[], sort: WishlistSort): Wish[] {
  const copy = [...items]
  switch (sort) {
    case 'reach':
      return copy.sort((a, b) => {
        const [sa, ma] = reachKey(a)
        const [sb, mb] = reachKey(b)
        return sa - sb || ma - mb || a.priority - b.priority
      })
    case 'priority':
      return copy.sort((a, b) => a.priority - b.priority)
    case 'cost':
      return copy.sort((a, b) => Number(b.cost) - Number(a.cost))
    case 'added':
      return copy.sort((a, b) => b.created_at.localeCompare(a.created_at))
    case 'name':
      return copy.sort((a, b) => a.name.localeCompare(b.name))
  }
}

/** The top priorities, whatever the list is sorted by, and everything else
 *  in the order given. */
export function splitHero(sorted: Wish[]): { hero: Wish[]; rest: Wish[] } {
  const byPriority = [...sorted].sort((a, b) => a.priority - b.priority)
  const hero = byPriority.slice(0, HERO_COUNT)
  const heroIds = new Set(hero.map((w) => w.id))
  return { hero, rest: sorted.filter((w) => !heroIds.has(w.id)) }
}

export function filterWishes(items: Wish[], projects: WishlistProject[], query: string): Wish[] {
  const q = query.trim().toLowerCase()
  if (!q) return items
  const projectName = new Map(projects.map((p) => [p.id, p.name.toLowerCase()]))
  return items.filter(
    (w) =>
      w.name.toLowerCase().includes(q) ||
      (w.notes ?? '').toLowerCase().includes(q) ||
      (w.project_id ? (projectName.get(w.project_id) ?? '').includes(q) : false)
  )
}

export interface ProjectSection {
  project: WishlistProject | null
  items: Wish[]
}

/** Sections in project order; wishes in no project come last as "Other wants". */
export function groupByProject(items: Wish[], projects: WishlistProject[]): ProjectSection[] {
  const ordered = [...projects].sort((a, b) => a.sort_order - b.sort_order)
  const sections: ProjectSection[] = ordered.map((project) => ({
    project,
    items: items.filter((w) => w.project_id === project.id),
  }))
  const loose = items.filter((w) => !w.project_id || !projects.some((p) => p.id === w.project_id))
  if (loose.length) sections.push({ project: null, items: loose })
  return sections
}

export function splitProjects(projects: WishlistProject[]): {
  active: WishlistProject[]
  complete: WishlistProject[]
} {
  return {
    active: projects.filter((p) => !p.summary.complete),
    complete: projects.filter((p) => p.summary.complete),
  }
}
