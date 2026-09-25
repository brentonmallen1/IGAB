/**
 * The pure half of a tag's checklist: grouping, filtering, and the diff a Save
 * sends. `CategoryMembershipList` renders it; `TagMembershipDialog` and the
 * emergency-fund picker both save it, so neither re-derives what changed.
 */
import type { MembershipCategory, MembershipChange } from '../../api/tags'
import type { SavingsMode } from '../../types'

export interface MembershipGroup {
  groupId: string
  groupName: string
  rows: MembershipCategory[]
}

/** What the person has ticked and chosen, keyed by category id. `modes` holds
 *  only rows whose mode was touched; untouched rows keep their stored choice. */
export interface MembershipDraft {
  checked: ReadonlySet<string>
  modes: Readonly<Record<string, SavingsMode | null>>
}

export function initialDraft(rows: readonly MembershipCategory[]): MembershipDraft {
  return { checked: new Set(rows.filter((r) => r.member).map((r) => r.id)), modes: {} }
}

export function toggleChecked(draft: MembershipDraft, id: string): MembershipDraft {
  const checked = new Set(draft.checked)
  if (checked.has(id)) checked.delete(id)
  else checked.add(id)
  return { ...draft, checked }
}

export function chooseMode(
  draft: MembershipDraft,
  id: string,
  mode: SavingsMode | null
): MembershipDraft {
  return { ...draft, modes: { ...draft.modes, [id]: mode } }
}

/** Rows in served (Budget-page) order, grouped by their group. A filter
 *  matching a group's name keeps the whole group; otherwise only the
 *  categories whose names match. Empty groups are dropped. */
export function groupRows(rows: readonly MembershipCategory[], filter = ''): MembershipGroup[] {
  const needle = filter.trim().toLocaleLowerCase()
  const groups: MembershipGroup[] = []
  const byId = new Map<string, MembershipGroup>()
  for (const row of rows) {
    const groupHit = needle !== '' && row.group_name.toLocaleLowerCase().includes(needle)
    if (needle && !groupHit && !row.name.toLocaleLowerCase().includes(needle)) continue
    let group = byId.get(row.group_id)
    if (!group) {
      group = { groupId: row.group_id, groupName: row.group_name, rows: [] }
      byId.set(row.group_id, group)
      groups.push(group)
    }
    group.rows.push(row)
  }
  return groups
}

/** Counted through another tag that implies this one (served `implied_by`),
 *  so it is not the household's to untick here: the checkbox is drawn ticked
 *  and disabled, with no mode control, and no save names it. */
export function isImplied(row: MembershipCategory): boolean {
  return row.implied_by !== null
}

/** Whether a row's checkbox is drawn ticked: implied rows always are,
 *  whatever the draft holds. */
export function drawsChecked(draft: MembershipDraft, row: MembershipCategory): boolean {
  return isImplied(row) || draft.checked.has(row.id)
}

/** The mode a checked row's control shows: what was touched, else the stored
 *  choice (null = the tags' default). */
export function draftMode(draft: MembershipDraft, row: MembershipCategory): SavingsMode | null {
  return row.id in draft.modes ? draft.modes[row.id] : row.savings_mode
}

/** Whether the default a row would get is already known from the server: the
 *  row's membership is unchanged and it is a savings category now, so its
 *  served role IS the default. A row being added or removed would get a role
 *  only the server can say — the control names no default for it. */
export function servedDefault(draft: MembershipDraft, row: MembershipCategory): SavingsMode | null {
  if (draft.checked.has(row.id) !== row.member) return null
  if (row.savings_mode !== null || row.savings_role === 'none') return null
  return row.savings_role
}

/** The change a Save sends: ids to add and remove against the loaded
 *  membership, and modes that differ from what is stored — for rows that are
 *  checked once saved (a removed row's mode is not this tag's to set). Never
 *  an implied row: adding the tag would change nothing but its tag list, and
 *  removing it could not take the row out — the server refuses both. */
export function membershipDiff(
  rows: readonly MembershipCategory[],
  draft: MembershipDraft
): MembershipChange {
  const change: MembershipChange = { add: [], remove: [], savings_modes: {} }
  for (const row of rows) {
    if (isImplied(row)) continue
    const checked = draft.checked.has(row.id)
    if (checked && !row.member) change.add.push(row.id)
    if (!checked && row.member) change.remove.push(row.id)
    if (checked && row.id in draft.modes && draft.modes[row.id] !== row.savings_mode) {
      change.savings_modes[row.id] = draft.modes[row.id]
    }
  }
  return change
}

export function isEmptyChange(change: MembershipChange): boolean {
  return (
    change.add.length === 0 &&
    change.remove.length === 0 &&
    Object.keys(change.savings_modes).length === 0
  )
}
