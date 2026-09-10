# Reports audit — local branch chain

An audit of all 30 reports raised 157 findings over 139 sites; an adversarial
verification pass confirmed 110 (4 critical, 52 major, the rest minor, plus 28
confirmed narrower than first claimed). Almost all of them are one question
answered from a different row set in a different report, so the work is ordered
by root cause rather than by report.

**These branches are deliberately local.** Nothing is pushed and no PR is opened
until the repo owner says so outside work hours. Push in the order below; if
opening a stacked PR set, each PR's base is the branch above it, and never
`--delete-branch` a base while its child PR is open.

This file is the chain of record. All branches live in the `~/repos/IGAB-reports` worktree, cut sequentially off
each other, starting from `origin/main` at `892922a0`.

| # | Branch | Scope | State |
|---|---|---|---|
| 1 | `fix/reports-month-formatter` | One short-month and day-month formatter; kill the `toISOString` round-trip; Anomalies uses the shared month window | done |
| 2 | `fix/reports-tooltip-and-axes` | `ChartTooltip` requires a formatter; eight money axes onto `useMoneyAxis`; privacy-mode leaks | done |
| 3 | `fix/reports-projection-recurrence` | `cash_projection` reuses `domain/schedule.py`; subscription/schedule dedup; recency window | done |
| 4 | `fix/reports-savings-carryover` | `savings_report` reuses `domain/carryover.py`; envelope set; window | done |
| 5 | `fix/reports-one-spending-row-set` | Clear items: class rule, sign-vs-class, scope conflation, names, drained envelopes | done |
| 5b | `fix/reports-tagged-envelope-spend` | Spending out of a savings-tagged envelope counts against its plan (decided) | todo |
| 6 | `fix/reports-one-window` | One report window; partial-current-month rule; honest denominators | todo |
| 7 | `fix/reports-payday-denominators` | payday-effect divisors and the P75 threshold | todo |
| 8 | `fix/reports-split-parent-leaf` | Sankey income, timeline class + scope on split rows | todo |
| 9 | `fix/reports-totals-not-truncations` | A truncated set is not a total (payee_analysis, DrillDownTable, Pareto) | todo |
| 10 | `fix/reports-scope-plumbing` | `_parse_uuids` widening; param bounds; `filter_unavailable` | todo |
| 11 | `fix/reports-contract-drift` | Duplicate interfaces; required served fields; empty paths | todo |
| 12 | `fix/reports-labels` | Labels that contradict the computation | todo |
| 13 | `fix/reports-efficiency` | Per-month query loops; whole-register scans; CSV amount formatting | todo |

Branches 1–4 are independent in content and could be reordered; 5 onward depend
on the extractions beneath them.
