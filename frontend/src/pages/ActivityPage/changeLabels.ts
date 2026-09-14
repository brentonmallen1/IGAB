/** Human labels for change-log rows — the Activity page and the global undo toast share them. */

const ENTITY_LABELS: Record<string, string> = {
  transaction: 'transaction',
  payee: 'payee',
  category: 'category',
  category_group: 'category group',
  assignment: 'assignment',
  wishlist_item: 'wishlist item',
  wishlist_project: 'wishlist project',
  // The reorder pseudo-subject for wishes/projects, like 'budget' below.
  wishlist: 'wishlist',
  category_target: 'target',
  liability: 'liability',
  liability_snapshot: 'balance point',
  asset: 'asset',
  asset_value: 'value point',
  scheduled_transaction: 'scheduled transaction',
  budget_view: 'view',
  budget_filter: 'filter',
  tag: 'tag',
  // Membership pseudo-subjects: the entity is the category/payee whose tag
  // set moved.
  category_tags: 'category tags',
  payee_tags: 'payee tags',
  account: 'account',
  account_type: 'account type',
  reconciliation: 'reconciliation',
  transaction_match: 'duplicate match',
  category_plan: 'plan',
  guide_state: 'guide setting',
  guide_binding: 'guide answer',
  budget_member: 'member',
  attachment: 'attachment',
}

export function entityTypeLabel(entityType: string, action?: string): string {
  if (entityType === 'budget') {
    // The subject of plain settings updates AND — as a pseudo-subject —
    // of a reorder of its category groups.
    return action === 'reorder' ? 'category groups' : 'budget'
  }
  // Unknown types fall through as-is rather than crashing — a new backend
  // entity renders snake_case until this map learns it.
  return ENTITY_LABELS[entityType] ?? entityType
}

const ACTION_LABELS: Record<string, string> = {
  create: 'Created',
  update: 'Updated',
  delete: 'Deleted',
  approve: 'Approved',
  import: 'Imported',
  merge: 'Merged',
  reorder: 'Reordered',
  archive: 'Archived',
  unarchive: 'Unarchived',
}

export function actionTypeLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}

/**
 * What a `guide_state` write changed, for the keys a person can name. The row
 * records `{_key, _value}` (`guide/repo.py::set_state_recorded`), which the
 * field-diff summary skips as bookkeeping — so a flipped setting read as an
 * update with no summary at all. Unknown keys return null and the card keeps
 * its generic label.
 */
export function guideStateSummary(after: Record<string, unknown> | null): string | null {
  const key = after?._key
  const value = after?._value as Record<string, unknown> | null | undefined
  if (key === 'reports:spread_sinking_funds') {
    // No row is on (`services/report_settings.py`).
    const on = !(value && value.on === false)
    return `Spread yearly bills over 12 months: ${on ? 'on' : 'off'}`
  }
  return null
}
