import { TAB_FILTER_SUPPORT, type ReportFilters, type ReportTab } from '../../../stores/reportStore'

/**
 * How many scope choices are in force — what the phone's Filters chip
 * counts, and what decides whether Reset is offered. One definition: the
 * bar used to compute "has filters" inline, and a chip that counted
 * differently would say 2 over a bar that offered no Reset.
 *
 * Dates and group-by are not counted: every report has a range and a
 * rollup, so neither is a narrowing the reader chose.
 */
export function countActiveFilters(f: ReportFilters): number {
  return (
    (f.categoryIds.length > 0 ? 1 : 0) +
    (f.tagIds.length > 0 ? 1 : 0) +
    (f.filterId !== null ? 1 : 0) +
    (f.payeeIds.length > 0 ? 1 : 0) +
    (f.accountIds.length > 0 ? 1 : 0) +
    (f.viewId !== null ? 1 : 0)
  )
}

/** Whether this report takes any scope at all; a bar with nothing in it is not drawn. */
export function hasAnyFilterSupport(activeTab: ReportTab): boolean {
  const support = TAB_FILTER_SUPPORT[activeTab]
  return !!(
    support.dates ||
    support.categories ||
    support.payees ||
    support.accounts ||
    support.groupBy ||
    support.views
  )
}
