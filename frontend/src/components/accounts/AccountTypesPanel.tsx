import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  useAccountTypes,
  useCreateAccountType,
  useDeleteAccountType,
  useUpdateAccountType,
  type AccountTypeInfo,
} from '../../api/accountTypes'
import { apiErrorMessage } from '../../api/client'
import { confirmAsync } from '../../stores/confirmStore'
import './AccountTypesPanel.css'

interface Props {
  budgetId: string
}

/** Manage this budget's account types: built-ins are shown read-only; custom
 * types can be added, edited, and deleted (while unused). */
export function AccountTypesPanel({ budgetId }: Props) {
  const { data: types = [] } = useAccountTypes(budgetId)
  const createType = useCreateAccountType(budgetId)
  const updateType = useUpdateAccountType(budgetId)
  const deleteType = useDeleteAccountType(budgetId)

  // null = closed, 'new' = add form, otherwise the id being edited
  const [formTarget, setFormTarget] = useState<string | null>(null)
  const [label, setLabel] = useState('')
  const [classification, setClassification] = useState<'asset' | 'liability'>('asset')
  const [defaultOnBudget, setDefaultOnBudget] = useState(false)
  const [description, setDescription] = useState('')

  function openForm(target: AccountTypeInfo | 'new') {
    if (target === 'new') {
      setFormTarget('new')
      setLabel('')
      setClassification('asset')
      setDefaultOnBudget(false)
      setDescription('')
    } else {
      setFormTarget(target.id)
      setLabel(target.label)
      setClassification(target.classification)
      setDefaultOnBudget(target.default_on_budget)
      setDescription(target.description ?? '')
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!label.trim() || !formTarget) return
    const payload = {
      label: label.trim(),
      classification,
      default_on_budget: defaultOnBudget,
      description: description.trim() || null,
    }
    try {
      if (formTarget === 'new') {
        await createType.mutateAsync(payload)
      } else {
        await updateType.mutateAsync({ id: formTarget, ...payload })
      }
      setFormTarget(null)
    } catch (err: unknown) {
      toast.error(apiErrorMessage(err, 'Failed to save account type'))
    }
  }

  async function handleDelete(t: AccountTypeInfo) {
    const ok = await confirmAsync({
      title: `Delete account type "${t.label}"?`,
      message: 'Only types with no accounts can be deleted.',
      confirmLabel: 'Delete type',
      destructive: true,
    })
    if (!ok) return
    try {
      await deleteType.mutateAsync(t.id)
    } catch (err: unknown) {
      toast.error(apiErrorMessage(err, 'Failed to delete account type'))
    }
  }

  const pending = createType.isPending || updateType.isPending

  return (
    <div className="acct-types surface">
      <div className="acct-types__header">
        <div>
          <div className="acct-types__title">Account Types</div>
          <div className="acct-types__hint">
            A type decides whether an account counts as an asset or a liability, and whether
            new accounts of that type start on budget. Built-in types can't be changed.
            {' '}For accounts kept <em>off</em> budget, these two answers also decide how
            money you move there is read: into an asset it counts as saving, toward a
            liability it counts as paying down debt. Neither is spending.
          </div>
        </div>
        <button
          className="acct-types__add-btn"
          onClick={() => openForm('new')}
          disabled={formTarget === 'new'}
        >
          <Plus size={14} />
          <span>New type</span>
        </button>
      </div>

      <div className="acct-types__list">
        {types.map((t) => (
          <div key={t.id} className="acct-types__row">
            <span className="acct-types__label" title={t.description ?? undefined}>
              {t.label}
            </span>
            <span className={`acct-types__chip acct-types__chip--${t.classification}`}>
              {t.classification}
            </span>
            <span className="acct-types__chip">
              {t.default_on_budget ? 'on budget' : 'off budget'}
            </span>
            {t.is_system ? (
              <span className="acct-types__system">built-in</span>
            ) : (
              <span className="acct-types__actions">
                <button
                  className="acct-types__icon-btn"
                  onClick={() => openForm(t)}
                  title="Edit type"
                  aria-label={`Edit ${t.label}`}
                >
                  <Pencil size={13} />
                </button>
                <button
                  className="acct-types__icon-btn acct-types__icon-btn--danger"
                  onClick={() => handleDelete(t)}
                  disabled={deleteType.isPending}
                  title="Delete type"
                  aria-label={`Delete ${t.label}`}
                >
                  <Trash2 size={13} />
                </button>
              </span>
            )}
          </div>
        ))}
      </div>

      {formTarget !== null && (
        <form className="acct-types__form" onSubmit={handleSubmit}>
          <div className="acct-types__form-row">
            <input
              className="acct-types__input"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Type name, e.g. Pension"
              maxLength={50}
              required
              autoFocus
            />
            <select
              className="acct-types__input"
              value={classification}
              onChange={(e) => setClassification(e.target.value as 'asset' | 'liability')}
            >
              <option value="asset">Asset (you own it)</option>
              <option value="liability">Liability (you owe it)</option>
            </select>
            <div className="acct-types__hint">
              Off budget, an asset makes incoming money count as saving and a liability
              makes it count as paying down debt. On budget, this only affects net worth.
            </div>
            <label className="acct-types__checkbox">
              <input
                type="checkbox"
                checked={defaultOnBudget}
                onChange={(e) => setDefaultOnBudget(e.target.checked)}
              />
              On budget by default
            </label>
          </div>
          <input
            className="acct-types__input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description shown wherever this type is offered…"
          />
          <div className="acct-types__form-actions">
            <button
              type="button"
              className="acct-types__btn"
              onClick={() => setFormTarget(null)}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="acct-types__btn acct-types__btn--primary"
              disabled={pending || !label.trim()}
            >
              {pending ? 'Saving…' : formTarget === 'new' ? 'Create type' : 'Save'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
