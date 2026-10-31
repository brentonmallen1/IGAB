import { describe, expect, it } from 'vitest'
import type { AIJob } from '../../../api/aiJobs'
import type { Transaction } from '../../../types'
import type { NamedCategory } from '../../../utils/categoryLabels'
import { jobSplitView, splitParentIds } from './jobSplitView'

const labels = new Map<string, NamedCategory>([
  ['garden', { name: 'Garden', group: 'Home' }],
  ['tools', { name: 'Tools', group: 'Home' }],
])

const job = (over: Partial<AIJob> = {}): AIJob =>
  ({
    id: 'job-1',
    transaction_id: 'txn-1',
    transaction_account_id: 'checking',
    transaction_is_split: false,
    result: {
      suggested_split: [
        { category: 'Garden', amount: '-15.00' },
        { category: 'Tools', amount: '-9.00' },
      ],
    },
    ...over,
  }) as AIJob

const line = (category_id: string | null, amount: number) =>
  ({ id: `${category_id}`, category_id, amount }) as Transaction

describe('jobSplitView', () => {
  it('itemises a split row from its lines as they stand, not from the read', () => {
    // A line moved to Tools since the scan reads as Tools.
    const view = jobSplitView(
      job({ transaction_is_split: true }),
      [line('tools', -20), line(null, -4)],
      labels
    )
    expect(view).toEqual({
      kind: 'filed',
      lines: [
        { label: 'Tools', amount: -20 },
        { label: 'Uncategorized', amount: -4 },
      ],
    })
  })

  it('draws nothing for a split row until its lines arrive', () => {
    expect(jobSplitView(job({ transaction_is_split: true }), undefined, labels)).toBeNull()
  })

  it('shows the model’s split beside a row filed in one category', () => {
    expect(jobSplitView(job(), undefined, labels)).toEqual({
      kind: 'suggested',
      lines: [
        { label: 'Garden', amount: -15 },
        { label: 'Tools', amount: -9 },
      ],
    })
  })

  it('says nothing with no row, or no split either way', () => {
    expect(jobSplitView(job({ transaction_id: null }), undefined, labels)).toBeNull()
    expect(jobSplitView(job({ transaction_account_id: null }), undefined, labels)).toBeNull()
    expect(jobSplitView(job({ result: { suggested_split: null } }), undefined, labels)).toBeNull()
  })
})

describe('splitParentIds', () => {
  it('asks lines only for the split rows that exist', () => {
    const jobs = [
      job({ id: 'a', transaction_id: 'split-row', transaction_is_split: true }),
      job({ id: 'b', transaction_id: 'one-row' }),
      job({ id: 'c', transaction_id: null, transaction_is_split: false }),
    ]
    expect(splitParentIds(jobs)).toEqual(['split-row'])
  })
})
