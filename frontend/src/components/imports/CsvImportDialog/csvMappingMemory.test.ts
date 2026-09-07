/**
 * Remembering what a bank's export looks like.
 *
 * The value is small and the failure modes are not: pre-filling a mapping
 * with a column the file no longer has would get the import refused for a
 * reason the user did not cause, and remembering one account's layout for
 * another would file transactions by the wrong columns entirely.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { applicableMapping, rememberMapping, rememberedMapping } from './csvMappingMemory'

const HARBORSTONE = 'acct-1'
const SAPPHIRE = 'acct-2'

beforeEach(() => {
  localStorage.clear()
})

describe('csv mapping memory', () => {
  it('remembers per account, not per app', () => {
    // Two banks, two layouts. Sharing one would file by the wrong columns.
    rememberMapping(HARBORSTONE, { date: 'Posted Date', amount: 'Amount' })
    rememberMapping(SAPPHIRE, { date: 'Fecha', amount: 'Importe' })

    expect(rememberedMapping(HARBORSTONE)?.date).toBe('Posted Date')
    expect(rememberedMapping(SAPPHIRE)?.date).toBe('Fecha')
  })

  it('has nothing to say about an account it has not seen', () => {
    expect(rememberedMapping('unknown')).toBeUndefined()
  })

  it('offers the mapping back when the file still has those columns', () => {
    rememberMapping(HARBORSTONE, { date: 'Posted Date', payee: 'Description' })

    expect(applicableMapping(HARBORSTONE, ['Posted Date', 'Description', 'Amount'])).toEqual({
      date: 'Posted Date',
      payee: 'Description',
    })
  })

  it('drops a field whose column the bank renamed', () => {
    // Pre-filling "Description" against a file that no longer has it would
    // be refused by the server for something the user did not do.
    rememberMapping(HARBORSTONE, { date: 'Posted Date', payee: 'Description' })

    expect(applicableMapping(HARBORSTONE, ['Posted Date', 'Merchant'])).toEqual({
      date: 'Posted Date',
    })
  })

  it('offers nothing when none of the remembered columns survive', () => {
    // Undefined, not {}: an empty mapping means "map nothing", which is a
    // different instruction from "no opinion".
    rememberMapping(HARBORSTONE, { date: 'Posted Date' })

    expect(applicableMapping(HARBORSTONE, ['Fecha', 'Importe'])).toBeUndefined()
  })

  it('survives storage it cannot read', () => {
    localStorage.setItem('igab.csvMapping', 'not json')
    expect(rememberedMapping(HARBORSTONE)).toBeUndefined()
  })

  it('says nothing and throws nothing when storage refuses to write', () => {
    // A private window, or a browser set to block site data. Forgetting the
    // mapping is the worst this may cost — the import itself succeeded.
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(() => rememberMapping(HARBORSTONE, { date: 'Posted Date' })).not.toThrow()
    setItem.mockRestore()
  })
})
