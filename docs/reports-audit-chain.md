# Reports audit — local branch chain

An audit of all 30 reports raised 157 findings over 139 sites; an adversarial
verification pass confirmed 110 (4 critical, 52 major, the rest minor, plus 28
confirmed narrower than first claimed). Almost all of them are one question
answered from a different row set in a different report, so the work is ordered
by root cause rather than by report.

**Pushed and opened as a stacked PR set, #177 through #183**, base of each being
the branch above it. Merge bottom-up, #177 first.

**Never `--delete-branch` a base while its child PR is open** — it auto-closes
the child. Delete a branch only once every PR above it has merged.

Branches created after #183 branch off `feat/necessity-tiers` and continue the
stack.

This file is the chain of record. All branches live in the `~/repos/IGAB-reports` worktree, cut sequentially off
each other, starting from `origin/main` at `892922a0`.

| # | Branch | Scope | State |
|---|---|---|---|
| 1 | [#177](https://github.com/brentonmallen1/IGAB/pull/177) `fix/reports-month-formatter` | One short-month and day-month formatter; kill the `toISOString` round-trip; Anomalies uses the shared month window | done |
| 2 | [#178](https://github.com/brentonmallen1/IGAB/pull/178) `fix/reports-tooltip-and-axes` | `ChartTooltip` requires a formatter; eight money axes onto `useMoneyAxis`; privacy-mode leaks | done |
| 3 | [#179](https://github.com/brentonmallen1/IGAB/pull/179) `fix/reports-projection-recurrence` | `cash_projection` reuses `domain/schedule.py`; subscription/schedule dedup; recency window | done |
| 4 | [#180](https://github.com/brentonmallen1/IGAB/pull/180) `fix/reports-savings-carryover` | `savings_report` reuses `domain/carryover.py`; envelope set; window | done |
| 5 | [#181](https://github.com/brentonmallen1/IGAB/pull/181) `fix/reports-one-spending-row-set` | Clear items: class rule, sign-vs-class, scope conflation, names, drained envelopes | done |
| 5b | [#182](https://github.com/brentonmallen1/IGAB/pull/182) `fix/reports-lte-is-a-cost` | Long-term expense stops classifying a bill as saving; importer stops auto-writing it | done |
| 5c | [#183](https://github.com/brentonmallen1/IGAB/pull/183) `feat/necessity-tiers` | Essentials ⊂ Cost of Living as two nested tiers, with the gap and a standing | done |
| 6 | [#184](https://github.com/brentonmallen1/IGAB/pull/184) `fix/reports-one-window` | Window bounds: burn rate, net worth, volatility, seasonality, anomalies | done |
| 7 | `fix/reports-payday-denominators` | payday-effect divisors and the P75 threshold | todo |
| 8 | `fix/reports-split-parent-leaf` | Sankey income, timeline class + scope on split rows | todo |
| 9 | `fix/reports-totals-not-truncations` | A truncated set is not a total (payee_analysis, DrillDownTable, Pareto) | todo |
| 10 | `fix/reports-scope-plumbing` | `_parse_uuids` widening; param bounds; `filter_unavailable` | todo |
| 11 | `fix/reports-contract-drift` | Duplicate interfaces; required served fields; empty paths | todo |
| 12 | `fix/reports-labels` | Labels that contradict the computation | todo |
| 13 | `fix/reports-efficiency` | Per-month query loops; whole-register scans; CSV amount formatting | todo |

Branches 1–4 are independent in content and could be reordered; 5 onward depend
on the extractions beneath them.
