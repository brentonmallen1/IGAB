import { useState } from 'react'
import { ShieldCheck, UserMinus, UserPlus, X } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  useAddBudgetMember,
  useBudgetMembers,
  useRemoveBudgetMember,
} from '../../api/budgetMembers'
import { useUsers } from '../../api/users'
import { useCurrentUser } from '../../api/auth'
import { apiErrorMessage } from '../../api/client'
import { confirmAsync } from '../../stores/confirmStore'
import { Modal } from '../common/Modal/Modal'
import './SharingModal.css'

/**
 * Budget membership management, opened from the budget card's menu.
 *
 * Owners add/remove members; a member sees the roster and can leave. The
 * backend enforces everything (owner gates, last-owner protection) — this
 * modal just avoids offering actions that would 403.
 */
export function SharingModal({
  budgetId,
  budgetName,
  onClose,
}: {
  budgetId: string
  budgetName: string
  onClose: () => void
}) {
  const { data: me } = useCurrentUser()
  const { data: members = [], isLoading } = useBudgetMembers(budgetId)
  const { data: users = [] } = useUsers()
  const addMember = useAddBudgetMember(budgetId)
  const removeMember = useRemoveBudgetMember(budgetId)
  const [selectedUserId, setSelectedUserId] = useState('')

  const myRole = members.find((m) => m.user_id === me?.id)?.role
  const isOwner = myRole === 'owner'
  const memberIds = new Set(members.map((m) => m.user_id))
  const addable = users.filter((u) => u.is_active && !memberIds.has(u.id))

  async function handleAdd() {
    if (!selectedUserId) return
    try {
      await addMember.mutateAsync(selectedUserId)
      setSelectedUserId('')
    } catch (err: unknown) {
      toast.error(apiErrorMessage(err, 'Could not share the budget'))
    }
  }

  async function handleRemove(userId: string, label: string) {
    const leaving = userId === me?.id
    const ok = await confirmAsync({
      title: leaving ? `Leave "${budgetName}"?` : `Remove ${label}?`,
      message: leaving
        ? 'You will lose access until an owner shares it with you again.'
        : `${label} will immediately lose access to this budget.`,
      confirmLabel: leaving ? 'Leave budget' : 'Remove',
      destructive: true,
    })
    if (!ok) return
    try {
      await removeMember.mutateAsync(userId)
      if (leaving) onClose()
    } catch (err: unknown) {
      toast.error(apiErrorMessage(err, 'Could not remove the member'))
    }
  }

  return (
    <Modal onClose={onClose} historyKey="budget-sharing">
      <div
        className="sharing-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Sharing for ${budgetName}`}
      >
        <div className="sharing-modal__header">
          <div className="sharing-modal__title">Sharing — {budgetName}</div>
          <button className="sharing-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="sharing-modal__body">
          {isLoading ? (
            <div className="sharing-modal__loading">Loading…</div>
          ) : (
            <div className="sharing-modal__members">
              {members.map((m) => {
                const label = m.display_name || m.email
                const canRemove = isOwner || m.user_id === me?.id
                return (
                  <div key={m.user_id} className="sharing-modal__member">
                    <div className="sharing-modal__member-id">
                      <span className="sharing-modal__member-name">
                        {label}
                        {m.user_id === me?.id && <span className="sharing-modal__you">you</span>}
                      </span>
                      <span className="sharing-modal__role">
                        {m.role === 'owner' && <ShieldCheck size={11} />}
                        {m.role}
                      </span>
                    </div>
                    {canRemove && (
                      <button
                        className="sharing-modal__remove"
                        onClick={() => void handleRemove(m.user_id, label)}
                        title={m.user_id === me?.id ? 'Leave this budget' : `Remove ${label}`}
                      >
                        <UserMinus size={13} />
                        {m.user_id === me?.id ? 'Leave' : 'Remove'}
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {isOwner && (
            <div className="sharing-modal__add">
              {addable.length === 0 ? (
                <div className="sharing-modal__hint">
                  Everyone in the household already has access. New people are added in Settings →
                  Users first.
                </div>
              ) : (
                <>
                  <select
                    className="sharing-modal__select"
                    value={selectedUserId}
                    onChange={(e) => setSelectedUserId(e.target.value)}
                    aria-label="User to share with"
                  >
                    <option value="">Share with…</option>
                    {addable.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.display_name ? `${u.display_name} (${u.email})` : u.email}
                      </option>
                    ))}
                  </select>
                  <button
                    className="sharing-modal__add-btn"
                    onClick={() => void handleAdd()}
                    disabled={!selectedUserId || addMember.isPending}
                  >
                    <UserPlus size={14} />
                    {addMember.isPending ? 'Sharing…' : 'Share'}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
