/**
 * The conversion rules three surfaces share (editor, selection bar, inline
 * payee picker). Each case here is a request that must come out identical
 * whichever surface asked for it — a link made from the register and one
 * made in the editor are the same money movement.
 */
import { describe, expect, it } from 'vitest'
import {
  CREATE_NEW_PARTNER,
  awaitingPartnerChoice,
  mayBecomeTransfer,
  transferLinkFields,
  transferOptionAccountId,
  transferOptions,
  transferTargets,
} from './transferConversion'
import type { Account, Transaction } from '../../types'

const accounts = [
  { id: 'a1', name: 'Harborstone Checking', is_closed: false },
  { id: 'a2', name: 'Sapphire Visa', is_closed: false },
  { id: 'a3', name: 'Cascade Point HYSA', is_closed: true },
] as unknown as Account[]

describe('transferLinkFields', () => {
  it('sends the link alone when nothing is ambiguous', () => {
    expect(transferLinkFields('a2', null)).toEqual({ transfer_account_id: 'a2' })
  })

  it('names the row the user picked as the far leg', () => {
    expect(transferLinkFields('a2', 't-9')).toEqual({
      transfer_account_id: 'a2',
      transfer_partner_transaction_id: 't-9',
    })
  })

  it('asks for a far leg to be written when the user says none of these', () => {
    expect(transferLinkFields('a2', CREATE_NEW_PARTNER)).toEqual({
      transfer_account_id: 'a2',
      transfer_create_partner: true,
    })
  })

  it('never carries money fields — the server refuses a link that does', () => {
    const fields = transferLinkFields('a2', 't-9') as Record<string, unknown>
    expect('amount' in fields).toBe(false)
    expect('date' in fields).toBe(false)
  })
})

describe('awaitingPartnerChoice', () => {
  const candidates = [{ id: 't-9' }] as Transaction[]

  it('holds the save while candidates exist and none is picked', () => {
    expect(awaitingPartnerChoice(candidates, null)).toBe(true)
  })

  it('releases it once the user answers', () => {
    expect(awaitingPartnerChoice(candidates, 't-9')).toBe(false)
    expect(awaitingPartnerChoice(candidates, CREATE_NEW_PARTNER)).toBe(false)
  })

  it('never asks when there is nothing to choose between', () => {
    expect(awaitingPartnerChoice([], null)).toBe(false)
  })
})

describe('transferTargets', () => {
  it('leaves out the row’s own account and every closed one', () => {
    expect(transferTargets(accounts, 'a1').map((a) => a.id)).toEqual(['a2'])
  })
})

describe('transferOptions', () => {
  it('puts destinations under their own heading, so a payee named “Online Transfer” cannot be mistaken for one', () => {
    expect(transferOptions(accounts, 'a1')).toEqual([
      { id: 'transfer:a2', label: 'Sapphire Visa', group: 'Transfer to account' },
    ])
  })

  it('round-trips the account id, and reads a real payee id as no destination', () => {
    expect(transferOptionAccountId('transfer:a2')).toBe('a2')
    expect(transferOptionAccountId('p1')).toBeNull()
    expect(transferOptionAccountId(null)).toBeNull()
  })
})

describe('mayBecomeTransfer', () => {
  const plain = {
    transfer_id: null,
    is_split: false,
    parent_transaction_id: null,
    cleared: 'cleared',
  } as unknown as Transaction

  it('offers the conversion on an ordinary unlinked row', () => {
    expect(mayBecomeTransfer(plain)).toBe(true)
  })

  it('leaves an already-linked leg alone — retargeting moves its partner', () => {
    expect(mayBecomeTransfer({ ...plain, transfer_id: 't-2' })).toBe(false)
  })

  it('refuses a split and a split line, as the server does', () => {
    expect(mayBecomeTransfer({ ...plain, is_split: true })).toBe(false)
    expect(mayBecomeTransfer({ ...plain, parent_transaction_id: 't-1' })).toBe(false)
  })

  it('refuses a reconciled row, matching the editor’s toggle', () => {
    expect(mayBecomeTransfer({ ...plain, cleared: 'reconciled' })).toBe(false)
  })
})
