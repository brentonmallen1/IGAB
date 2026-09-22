import type { ToolId } from '../content/roadmap'
import type { GuideTab } from '../stores/guideStore'

/**
 * Addresses inside the Guide, spelled once. A link from a report, the
 * glossary or the category inspector into a Guide tab (and a section of it)
 * goes through here, and the sections carry their ids from the same lists —
 * so a renamed anchor is a compile error, not a link that silently lands at
 * the top of the tab.
 */

/** The sections of "Setting money aside", in page order. */
export const ASIDE_ANCHORS = [
  'savings-modes',
  'which-tag',
  'emergency-fund',
  'sinking-funds',
  'means-trend',
  'savings-report',
] as const

export type AsideAnchor = (typeof ASIDE_ANCHORS)[number]

/** The sections of "Credit cards", in page order. */
export const CARDS_ANCHORS = [
  'how-cards-work',
  'how-you-use-it',
  'situations',
  'card-catch-outs',
] as const

export type CardsAnchor = (typeof CARDS_ANCHORS)[number]

/** A Guide tab to link to, and a section of it where the tab has sections. */
export type GuideLinkTarget =
  | { tab: Exclude<GuideTab, 'aside' | 'cards'>; anchor?: never }
  | { tab: 'aside'; anchor?: AsideAnchor }
  | { tab: 'cards'; anchor?: CardsAnchor }

/** "/guide?tab=money", or "/guide?tab=aside#savings-modes" with a section. */
export function guideTabHref(tab: GuideTab, anchor?: string): string {
  return `/guide?tab=${tab}${anchor ? `#${anchor}` : ''}`
}

/** A section of "Setting money aside". */
export function asideHref(anchor: AsideAnchor): string {
  return guideTabHref('aside', anchor)
}

/** A section of "Credit cards". */
export function cardsHref(anchor: CardsAnchor): string {
  return guideTabHref('cards', anchor)
}

/** A calculator on the Tools tab: "/guide?tab=tools&tool=emergency-fund". */
export function guideToolHref(tool: ToolId): string {
  return `/guide?tab=tools&tool=${tool}`
}
