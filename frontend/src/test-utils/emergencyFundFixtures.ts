// One invented emergency fund, for every test that renders the Counting line
// or the picker — so the surfaces are held to the same served facts.
import type { EmergencyFundPicker } from '../api/emergencyFund'
import type { Tag, TagMembership } from '../api/tags'
import { makeMembershipRow as row } from './factories'

export const FUND_PICKER: EmergencyFundPicker = {
  fund: {
    set_up: true,
    total: 9400,
    categories: [{ id: 'fund', name: 'Emergency Fund', balance: 2400 }],
    accounts: [{ id: 'reserve', name: 'Harborstone Reserve', balance: 6000 }],
    external: { declared: true, amount: 1000, as_of: '2026-09-01', note: 'credit union' },
  },
  account_candidates: [
    {
      id: 'hysa',
      name: 'Cascade Point HYSA',
      balance: 500,
      counts_as_savings: false,
      member: false,
    },
    {
      id: 'reserve',
      name: 'Harborstone Reserve',
      balance: 6000,
      counts_as_savings: true,
      member: true,
    },
  ],
}

export const FUND_COUNTING_LINE =
  'Emergency Fund envelope $2,400.00 · Harborstone Reserve $6,000.00 · kept elsewhere $1,000.00'

export const EMPTY_FUND_PICKER: EmergencyFundPicker = {
  fund: {
    set_up: false,
    total: null,
    categories: [],
    accounts: [],
    external: { declared: false, amount: null, as_of: null, note: null },
  },
  account_candidates: [],
}

export const EMERGENCY_FUND_TAG: Tag = {
  id: 'ef-tag',
  name: 'Emergency fund',
  system_key: 'emergency_fund',
  color_slot: 'green',
  category_count: 1,
  hand_settable: true,
}

export const FUND_MEMBERSHIP: TagMembership = {
  tag: { id: 'ef-tag', name: 'Emergency fund', system_key: 'emergency_fund', savings_tag: true },
  categories: [
    row({
      id: 'fund',
      name: 'Emergency Fund',
      group_id: 'g-goals',
      group_name: 'Goals',
      member: true,
      savings_role: 'kept_here',
    }),
    row({ id: 'groceries', name: 'Groceries' }),
  ],
}
