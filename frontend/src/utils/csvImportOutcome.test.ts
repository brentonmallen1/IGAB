import { describe, expect, it } from 'vitest'
import type { CsvImportResult, CsvPreview, CsvPreviewRow } from '../api/imports'
import {
  hasWork,
  isAlreadyHere,
  primaryLabel,
  resultMessage,
  rowTag,
  rowsToWrite,
} from './csvImportOutcome'

function preview(over: Partial<CsvPreview> = {}): CsvPreview {
  return {
    headers: [],
    mapping: {},
    date_format: '%Y-%m-%d',
    total_rows: 0,
    new_rows: 0,
    duplicate_rows: 0,
    matched_rows: 0,
    confirmed_rows: 0,
    review_rows: 0,
    skipped: [],
    sample: [],
    ...over,
  }
}

function line(over: Partial<CsvPreviewRow>): CsvPreviewRow {
  return {
    line: 2,
    date: '2026-01-03',
    amount: -84.12,
    payee: "TRADER JOE'S #552",
    memo: null,
    category: null,
    outcome: 'new',
    confirms: false,
    ...over,
  }
}

function result(over: Partial<CsvImportResult> = {}): CsvImportResult {
  return {
    imported: 0,
    skipped: 0,
    errors: [],
    matched: 0,
    confirmed: 0,
    review: 0,
    batch_id: 'b1',
    ...over,
  }
}

describe('what a CSV import will do', () => {
  it('writes new lines and lines queued for review', () => {
    expect(rowsToWrite(preview({ new_rows: 2, review_rows: 1, matched_rows: 9 }))).toBe(3)
  })

  it('has work when it only clears rows already here', () => {
    // The dialog used to refuse this file outright: every line matched, so
    // `new_rows` was 0, and the rows it would have cleared stayed uncleared.
    expect(hasWork(preview({ matched_rows: 6, confirmed_rows: 6 }))).toBe(true)
  })

  it('has no work when every line is already here and settled', () => {
    expect(hasWork(preview({ duplicate_rows: 3, matched_rows: 2 }))).toBe(false)
  })

  it('has work when the only line is one to review', () => {
    expect(hasWork(preview({ review_rows: 1 }))).toBe(true)
  })
})

describe('primaryLabel', () => {
  it('counts the rows it will write', () => {
    expect(primaryLabel(preview({ new_rows: 1 }))).toBe('Import 1 transaction')
    expect(primaryLabel(preview({ new_rows: 2, review_rows: 1 }))).toBe('Import 3 transactions')
  })

  it('says it will clear when nothing is written', () => {
    expect(primaryLabel(preview({ matched_rows: 6, confirmed_rows: 6 }))).toBe(
      'Clear 6 transactions'
    )
  })

  it('stays plain before a file and when there is nothing to do', () => {
    expect(primaryLabel(null)).toBe('Import')
    expect(primaryLabel(preview({ duplicate_rows: 4 }))).toBe('Import')
  })
})

describe('rowTag', () => {
  it.each([
    ['already_imported', false, 'already here', 'here'],
    ['matched', false, 'already here', 'here'],
    ['matched', true, 'will clear', 'clear'],
    ['review', false, 'to review', 'review'],
  ] as const)('%s (confirms=%s) reads "%s"', (outcome, confirms, label, tone) => {
    expect(rowTag(line({ outcome, confirms }))).toEqual({ label, tone })
  })

  it('leaves a plain new line untagged', () => {
    expect(rowTag(line({ outcome: 'new' }))).toBeNull()
  })

  it('dims every line nothing new is written for', () => {
    expect(isAlreadyHere(line({ outcome: 'matched', confirms: true }))).toBe(true)
    expect(isAlreadyHere(line({ outcome: 'already_imported' }))).toBe(true)
    expect(isAlreadyHere(line({ outcome: 'review' }))).toBe(false)
    expect(isAlreadyHere(line({ outcome: 'new' }))).toBe(false)
  })
})

describe('resultMessage', () => {
  it('names everything the import did', () => {
    expect(resultMessage(result({ imported: 3, confirmed: 6, review: 1 }))).toBe(
      'Imported 3 transactions · cleared 6 already here · 1 to review'
    )
  })

  it('reads as a sentence when it only cleared rows', () => {
    expect(resultMessage(result({ confirmed: 1, matched: 4 }))).toBe('Cleared 1 already here')
  })

  it('says so when it changed nothing', () => {
    expect(resultMessage(result({ matched: 4, skipped: 2, batch_id: null }))).toBe(
      'Nothing new to import — every row was already here'
    )
  })
})
