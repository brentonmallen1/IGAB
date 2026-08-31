/**
 * Every query-key root, spelled once.
 *
 * The bug this exists to make impossible: an invalidation naming a root no
 * query uses. It refreshes nothing, silently, and the symptom is "I had to
 * reload the page". `['category-transactions']` was invalidated at twelve
 * sites and was never a query key anywhere — the two drill-downs it was
 * aiming at (`transactionsPeek`, `budgetTransactions`) went stale after every
 * edit. `['netWorth']` and `['duplicatePayees']` were the same shape. And the
 * comment at the foot of `changes.ts` records an earlier one: `['category-groups']`
 * sat in a list for months quietly refreshing nothing, because the real root
 * is `categoryGroups`.
 *
 * A comment asking the next reader to keep two spellings in step is not a
 * mechanism. Both sides reading one constant is. So: **a query key's first
 * element comes from here, and so does an invalidation's** — the tail
 * arguments stay at the call site, where they are local and where React
 * Query's prefix matching makes their arity harmless.
 *
 * `queryKeys.deadRoots.test.ts` fails if a root here is never used by a real
 * query, which is the other half of the same guarantee: a root that no query
 * answers to cannot survive in this file either.
 *
 * Naming is inconsistent across roots (`budget-members` beside `budgetMonth`)
 * because it always was; the keys are wire-visible cache identity, and
 * renaming them is a separate change from giving them one home.
 */
export const ROOT = {
  accountHygiene: 'account-hygiene',
  accountTypes: 'account-types',
  accounts: 'accounts',
  aiInsights: 'ai-insights',
  aiJob: 'ai-job',
  aiJobForTxn: 'ai-job-for-txn',
  aiJobs: 'ai-jobs',
  aiJobsActive: 'ai-jobs-active',
  aiStatus: 'ai-status',
  allTransactions: 'all-transactions',
  archivedCategories: 'archivedCategories',
  assignPreview: 'assignPreview',
  assignStrategies: 'assignStrategies',
  attachmentBlob: 'attachmentBlob',
  attachmentCheck: 'attachmentCheck',
  attachments: 'attachments',
  backups: 'backups',
  budgetFilters: 'budgetFilters',
  budgetMembers: 'budget-members',
  budgetMonth: 'budgetMonth',
  budgetMoves: 'budgetMoves',
  budgetSnapshots: 'budget-snapshots',
  budgetTransactions: 'budget-transactions',
  budgetViews: 'budgetViews',
  budgets: 'budgets',
  categories: 'categories',
  categoryArchivePreview: 'categoryArchivePreview',
  categoryClassification: 'categoryClassification',
  categoryDeletePreview: 'categoryDeletePreview',
  categoryGroups: 'categoryGroups',
  categoryHistory: 'categoryHistory',
  categoryHistoryBatch: 'categoryHistoryBatch',
  changes: 'changes',
  coverOverspentPreview: 'coverOverspentPreview',
  currentUser: 'currentUser',
  guide: 'guide',
  guideCandidates: 'guide-candidates',
  guideCheckup: 'guide-checkup',
  guideScenario: 'guide-scenario',
  guideSignals: 'guide-signals',
  importSummary: 'importSummary',
  liabilities: 'liabilities',
  liabilityAmortization: 'liabilityAmortization',
  nearbyPayees: 'nearbyPayees',
  ollamaModels: 'ollama-models',
  paletteSearch: 'paletteSearch',
  payeeTransactions: 'payee-transactions',
  payees: 'payees',
  pendingMatchesAccount: 'pending-matches-account',
  pendingReviewCount: 'pending-review-count',
  pendingReviewCountAccount: 'pending-review-count-account',
  recentPayee: 'recentPayee',
  reconcileHistory: 'reconcile-history',
  reconcileStatus: 'reconcile-status',
  reports: 'reports',
  scheduledTransactions: 'scheduled-transactions',
  settings: 'settings',
  similarTransactions: 'similar-transactions',
  simplefinConfig: 'simplefin-config',
  simplefinConnections: 'simplefin-connections',
  simplefinMatches: 'simplefin-matches',
  simplefinRateLimit: 'simplefin-rate-limit',
  simplefinRemoteAccounts: 'simplefin-remote-accounts',
  system: 'system',
  tagSuggestions: 'tagSuggestions',
  tags: 'tags',
  target: 'target',
  targets: 'targets',
  transaction: 'transaction',
  transactionClassification: 'transaction-classification',
  transactionSplits: 'transaction-splits',
  transactions: 'transactions',
  transactionsPeek: 'transactions-peek',
  transferCandidates: 'transfer-candidates',
  users: 'users',
  wishlist: 'wishlist',
} as const

export type QueryRoot = (typeof ROOT)[keyof typeof ROOT]
