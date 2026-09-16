import { describe, expect, it } from 'vitest'
import type { MembershipCategory } from '../../api/tags'
import {
  chooseMode,
  draftMode,
  groupRows,
  initialDraft,
  isEmptyChange,
  membershipDiff,
  servedDefault,
  toggleChecked,
} from './membershipList'

function row(over: Partial<MembershipCategory>): MembershipCategory {
  return {
    id: 'c1',
    name: 'Groceries',
    group_id: 'g-everyday',
    group_name: 'Everyday',
    is_archived: false,
    member: false,
    savings_role: 'none',
    savings_mode: null,
    ...over,
  }
}

const ROWS = [
  row({
    id: 'fund',
    name: 'Emergency Fund',
    group_id: 'g-goals',
    group_name: 'Goals',
    member: true,
    savings_role: 'kept_here',
  }),
  row({
    id: 'general',
    name: 'General Savings',
    group_id: 'g-goals',
    group_name: 'Goals',
    savings_role: 'sent_out',
  }),
  row({ id: 'groceries', name: 'Groceries' }),
  row({ id: 'rent', name: 'Rent' }),
]

describe('groupRows', () => {
  it('keeps served order and groups by group', () => {
    expect(groupRows(ROWS).map((g) => [g.groupName, g.rows.map((r) => r.id)])).toEqual([
      ['Goals', ['fund', 'general']],
      ['Everyday', ['groceries', 'rent']],
    ])
  })

  it('filters by category name, case-insensitively, and drops empty groups', () => {
    expect(groupRows(ROWS, '  gRoC ').map((g) => [g.groupName, g.rows.map((r) => r.id)])).toEqual([
      ['Everyday', ['groceries']],
    ])
  })

  it('a group-name match keeps the whole group', () => {
    expect(groupRows(ROWS, 'goals').flatMap((g) => g.rows.map((r) => r.id))).toEqual([
      'fund',
      'general',
    ])
  })
})

describe('membershipDiff', () => {
  it('is empty for an untouched draft', () => {
    expect(isEmptyChange(membershipDiff(ROWS, initialDraft(ROWS)))).toBe(true)
  })

  it('adds, removes, and toggling back is no change', () => {
    let draft = initialDraft(ROWS)
    draft = toggleChecked(draft, 'fund')
    draft = toggleChecked(draft, 'groceries')
    draft = toggleChecked(draft, 'rent')
    draft = toggleChecked(draft, 'rent')
    expect(membershipDiff(ROWS, draft)).toEqual({
      add: ['groceries'],
      remove: ['fund'],
      savings_modes: {},
    })
  })

  it('sends a mode only where it differs from the stored choice, on checked rows', () => {
    let draft = initialDraft(ROWS)
    draft = chooseMode(draft, 'fund', 'sent_out')
    draft = toggleChecked(draft, 'general')
    draft = chooseMode(draft, 'general', null) // same as stored: nothing to send
    draft = chooseMode(draft, 'groceries', 'kept_here') // not checked: not this tag's
    expect(membershipDiff(ROWS, draft)).toEqual({
      add: ['general'],
      remove: [],
      savings_modes: { fund: 'sent_out' },
    })
  })

  it('sends null to put a stored choice back to the default', () => {
    const rows = [
      row({ id: 'x', member: true, savings_role: 'sent_out', savings_mode: 'sent_out' }),
    ]
    const draft = chooseMode(initialDraft(rows), 'x', null)
    expect(membershipDiff(rows, draft).savings_modes).toEqual({ x: null })
  })
})

describe('draftMode and servedDefault', () => {
  it('shows the touched mode, else the stored one', () => {
    const draft = chooseMode(initialDraft(ROWS), 'fund', 'sent_out')
    expect(draftMode(draft, ROWS[0])).toBe('sent_out')
    expect(draftMode(draft, ROWS[1])).toBeNull()
  })

  it('names the default only when the served role already is it', () => {
    const draft = initialDraft(ROWS)
    expect(servedDefault(draft, ROWS[0])).toBe('kept_here')
    // Being added: its role after the save is the server's to say.
    expect(servedDefault(toggleChecked(draft, 'groceries'), ROWS[2])).toBeNull()
    // Membership moving on a savings row changes what its default could be.
    expect(servedDefault(toggleChecked(draft, 'general'), ROWS[1])).toBeNull()
    const stored = row({
      id: 's',
      member: true,
      savings_role: 'sent_out',
      savings_mode: 'sent_out',
    })
    expect(servedDefault(initialDraft([stored]), stored)).toBeNull()
  })
})
