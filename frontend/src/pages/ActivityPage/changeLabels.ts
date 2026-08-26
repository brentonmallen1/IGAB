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
    default:
      return action
  }
}
