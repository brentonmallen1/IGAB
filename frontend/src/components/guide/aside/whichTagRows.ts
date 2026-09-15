/**
 * "Which tag do I use?" — what an envelope is for, and the tag (and savings
 * mode) that says so. Keys only: tag names come from `SYSTEM_TAG_HELP` and
 * mode words from `utils/savingsModes.ts`, so a renamed tag or mode cannot
 * leave this table saying the old word.
 */
import type { SavingsMode } from '../../../types'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'

export interface WhichTagRow {
  id: string
  /** "The envelope is for…" */
  purpose: string
  /** System tag keys; more than one reads "A or B". */
  tags: string[]
  /** The savings mode to pick, 'either' when both work, null for a tag with
   * no mode. */
  mode: SavingsMode | 'either' | null
  /** Marks `mode` as the tag's default rather than a choice to make. */
  modeIsDefault?: boolean
  note?: string
}

export const WHICH_TAG_ROWS: WhichTagRow[] = [
  {
    id: 'untracked-account',
    purpose: 'Money going to an account IGAB doesn’t track, like an IRA at another bank',
    tags: ['savings'],
    mode: 'sent_out',
  },
  {
    id: 'tracked-savings-account',
    purpose: 'Money moved each month to a savings account you track, like Cascade Point HYSA',
    tags: ['savings'],
    mode: 'either',
    note: 'While it’s in the budget counts it when you assign it; when it leaves the budget counts it when you move it off budget.',
  },
  {
    id: 'cushion',
    purpose: 'A cushion or goal you keep in the budget and might spend',
    tags: ['savings'],
    mode: 'kept_here',
  },
  {
    id: 'emergencies',
    purpose: 'Money for genuine emergencies',
    tags: ['emergency_fund'],
    mode: 'kept_here',
    modeIsDefault: true,
  },
  {
    id: 'planned-bill',
    purpose: 'A known bill or planned purchase: property tax, insurance, a vacation',
    tags: ['long_term_expense'],
    mode: null,
  },
  {
    id: 'cannot-cut',
    purpose: 'Something you can’t do without',
    tags: ['essential', 'cost_of_living'],
    mode: null,
    note: `These combine with ${systemTagName('long_term_expense')}: property tax is both.`,
  },
]

/** Every system tag key the table names — held to `SYSTEM_TAG_HELP` by a test. */
export function whichTagKeys(): string[] {
  return [...new Set(WHICH_TAG_ROWS.flatMap((row) => row.tags))]
}
