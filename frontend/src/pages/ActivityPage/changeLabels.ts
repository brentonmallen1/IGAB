/** Human labels for change-log rows — the Activity page and the global undo toast share them. */

export function entityTypeLabel(entityType: string): string {
  switch (entityType) {
    case 'transaction':
      return 'transaction'
    case 'payee':
      return 'payee'
    case 'category':
      return 'category'
    case 'category_group':
      return 'category group'
    case 'assignment':
      return 'assignment'
    case 'budget':
      // Only ever the subject of a reorder of its groups.
      return 'category groups'
    case 'wishlist_item':
      return 'wishlist item'
    case 'wishlist_project':
      return 'wishlist project'
    case 'wishlist':
      // The reorder pseudo-subject, like 'budget' above.
      return 'wishlist'
    case 'category_target':
      return 'target'
    default:
      return entityType
  }
}

export function actionTypeLabel(action: string): string {
  switch (action) {
    case 'create':
      return 'Created'
    case 'update':
      return 'Updated'
    case 'delete':
      return 'Deleted'
    case 'approve':
      return 'Approved'
    case 'import':
      return 'Imported'
    case 'merge':
      return 'Merged'
    case 'reorder':
      return 'Reordered'
    case 'archive':
      return 'Archived'
    case 'unarchive':
      return 'Unarchived'
    default:
      return action
  }
}
