import { normalizeOneOf } from './normalizeOneOf'

/**
 * "Target" or "Cover + target" — which figure Auto-Assign's target amount
 * sets an envelope to, where the server offers the choice.
 *
 * The amounts are the server's (`target_assigned` and
 * `cover_target_assigned`, TargetService); nothing here computes money. This
 * is only which of the two served figures each envelope takes, and so which
 * category ids travel as `cover_ids` — the inspector's several-selected
 * dialog and the Assign dropdown's preview both choose through it.
 */

/** Device-local: what Target Amount does with an overspent envelope when
 *  several are pressed at once. `ask` (the default) opens the choice, `target`
 *  takes the target amount everywhere, `cover` takes Cover + target wherever
 *  it is offered. */
export const TARGET_COVER_MODES = ['ask', 'target', 'cover'] as const

export type TargetCoverMode = (typeof TARGET_COVER_MODES)[number]

export const DEFAULT_TARGET_COVER_MODE: TargetCoverMode = 'ask'

export const TARGET_COVER_MODE_COPY: Record<TargetCoverMode, { label: string; desc: string }> = {
  ask: {
    label: 'Ask',
    desc: 'List the overspent categories and choose for each.',
  },
  target: {
    label: 'Target only',
    desc: 'Assign the target amount; spending already covered counts toward it.',
  },
  cover: {
    label: 'Cover + target',
    desc: 'Cover the spending, then assign the target on top.',
  },
}

/** A stored value this build does not know reads as the default. */
export function normalizeTargetCoverMode(value: unknown): TargetCoverMode {
  return normalizeOneOf(TARGET_COVER_MODES, value, DEFAULT_TARGET_COVER_MODE)
}

export type TargetCoverPick = 'target' | 'cover'

/**
 * Target Amount's figure for one envelope: the served Cover + target figure
 * when it was chosen (`covered`) and is offered, else the served target
 * amount. The client's one pick between two served figures, drawn before the
 * round-trip — the server makes the same pick when it applies
 * (`assign_service.pick_target_figure`), and both suites run
 * `shared/target_cover_cases.json`.
 */
export function pickTargetFigure(
  target: number,
  cover: number | null | undefined,
  covered: boolean
): number {
  return covered && cover != null ? Number(cover) : Number(target)
}

/** One envelope offered the choice, with both served figures. */
export interface TargetCoverRow {
  categoryId: string
  name: string
  /** What assigned becomes under Target (served `target_assigned`). */
  target: number
  /** What assigned becomes under Cover + target (served `cover_target_assigned`). */
  cover: number
}

/** The envelopes among `categoryIds` offered the choice: those the server
 *  served a `cover_target_assigned` for. */
export function coverRows(
  categoryIds: readonly string[],
  balances: readonly {
    category_id: string
    target_assigned: number | null
    cover_target_assigned: number | null
  }[],
  nameOf: (categoryId: string) => string
): TargetCoverRow[] {
  const selected = new Set(categoryIds)
  return balances
    .filter(
      (b) =>
        selected.has(b.category_id) &&
        b.cover_target_assigned !== null &&
        b.target_assigned !== null
    )
    .map((b) => ({
      categoryId: b.category_id,
      name: nameOf(b.category_id),
      target: Number(b.target_assigned),
      cover: Number(b.cover_target_assigned),
    }))
}

/** The ids that start as Cover + target under `mode`: every offered one for
 *  `cover`, none otherwise — `ask` starts on Target and lets the person
 *  change it. */
export function initialCoverIds(mode: TargetCoverMode, offered: readonly string[]): string[] {
  return mode === 'cover' ? [...offered] : []
}

/** Whether pressing Target Amount should stop and ask first. */
export function shouldAskTargetCover(mode: TargetCoverMode, offeredCount: number): boolean {
  return mode === 'ask' && offeredCount > 0
}

/** The "same for all" control's state: the pick every row shares, or null
 *  when they differ. */
export function sharedPick(
  offered: readonly string[],
  coverIds: ReadonlySet<string>
): TargetCoverPick | null {
  if (offered.length === 0) return null
  const covered = offered.filter((id) => coverIds.has(id)).length
  if (covered === 0) return 'target'
  if (covered === offered.length) return 'cover'
  return null
}

/** `coverIds` with one envelope's pick applied. */
export function withPick(
  coverIds: ReadonlySet<string>,
  categoryId: string,
  pick: TargetCoverPick
): Set<string> {
  const next = new Set(coverIds)
  if (pick === 'cover') next.add(categoryId)
  else next.delete(categoryId)
  return next
}
