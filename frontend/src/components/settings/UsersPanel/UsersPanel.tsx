import { useState } from 'react'
import { KeyRound, ShieldCheck, UserPlus, UserX } from 'lucide-react'
import toast from 'react-hot-toast'
import { useCreateUser, useUpdateUser, useUsers, type ManagedUser } from '../../../api/users'
import { useCurrentUser } from '../../../api/auth'
import { apiErrorMessage } from '../../../api/client'
import { confirmAsync } from '../../../stores/confirmStore'
import { Dialog } from '../../common/Dialog/Dialog'
import './UsersPanel.css'

/**
 * Admin-only household user administration: create accounts, rename,
 * deactivate/reactivate, and reset passwords. No hard delete by design —
 * deleting a user would cascade into every budget they created; deactivation
 * revokes access (existing tokens die at the next lookup) without destroying
 * history. The env-bootstrapped admin's credential belongs to ADMIN_PASSWORD,
 * so its row offers no reset.
 */
export function UsersPanel() {
  const { data: users = [], isLoading } = useUsers()
  const { data: me } = useCurrentUser()
  const createUser = useCreateUser()
  const updateUser = useUpdateUser()

  const [newEmail, setNewEmail] = useState('')
  const [newName, setNewName] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [resetTarget, setResetTarget] = useState<ManagedUser | null>(null)

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    try {
      await createUser.mutateAsync({
        email: newEmail.trim(),
        password: newPassword,
        display_name: newName.trim() || null,
      })
      toast.success(`Added ${newEmail.trim()}`)
      setNewEmail('')
      setNewName('')
      setNewPassword('')
    } catch (err: unknown) {
      toast.error(apiErrorMessage(err, 'Could not create the user'))
    }
  }

  async function handleToggleActive(user: ManagedUser) {
    if (user.is_active) {
      const ok = await confirmAsync({
        title: `Deactivate ${user.display_name || user.email}?`,
        message:
          'They will be signed out and unable to log in until reactivated. ' +
          'Their budgets and history are kept.',
        confirmLabel: 'Deactivate',
        destructive: true,
      })
      if (!ok) return
    }
    try {
      await updateUser.mutateAsync({ id: user.id, is_active: !user.is_active })
    } catch (err: unknown) {
      toast.error(apiErrorMessage(err, 'Could not update the user'))
    }
  }

  if (isLoading) return <div className="users-panel__loading">Loading…</div>

  return (
    <div className="users-panel">
      <div className="users-panel__list">
        {users.map((u) => (
          <div
            key={u.id}
            className={`users-panel__row ${u.is_active ? '' : 'users-panel__row--inactive'}`}
          >
            <div className="users-panel__identity">
              <span className="users-panel__name">
                {u.display_name || u.email}
                {u.is_admin && (
                  <span className="users-panel__chip" title="Administrator">
                    <ShieldCheck size={11} /> admin
                  </span>
                )}
                {!u.is_active && (
                  <span className="users-panel__chip users-panel__chip--inactive">deactivated</span>
                )}
                {u.id === me?.id && <span className="users-panel__chip">you</span>}
              </span>
              {u.display_name && <span className="users-panel__email">{u.email}</span>}
            </div>
            <div className="users-panel__actions">
              {u.is_env_admin ? (
                <span
                  className="users-panel__env-note"
                  title="This credential is set by the ADMIN_PASSWORD environment variable and re-synced at every boot"
                >
                  managed by ADMIN_PASSWORD
                </span>
              ) : (
                <button
                  className="users-panel__btn"
                  onClick={() => setResetTarget(u)}
                  title={`Reset ${u.email}'s password`}
                >
                  <KeyRound size={13} />
                  Reset password
                </button>
              )}
              {u.id !== me?.id && (
                <button
                  className={`users-panel__btn ${u.is_active ? 'users-panel__btn--danger' : ''}`}
                  onClick={() => void handleToggleActive(u)}
                >
                  <UserX size={13} />
                  {u.is_active ? 'Deactivate' : 'Reactivate'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <form className="users-panel__add" onSubmit={handleAdd}>
        <div className="users-panel__add-fields">
          <input
            className="settings-input"
            type="email"
            placeholder="email@example.com"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
            autoComplete="off"
          />
          <input
            className="settings-input"
            type="text"
            placeholder="Display name (optional)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <input
            className="settings-input"
            type="password"
            placeholder="Initial password (min 8)"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            minLength={8}
            required
            autoComplete="new-password"
          />
        </div>
        <button
          type="submit"
          className="settings-btn settings-btn--primary users-panel__add-btn"
          disabled={createUser.isPending || !newEmail.trim() || newPassword.length < 8}
        >
          <UserPlus size={14} />
          {createUser.isPending ? 'Adding…' : 'Add user'}
        </button>
      </form>

      {resetTarget && (
        <ResetPasswordDialog
          user={resetTarget}
          onClose={() => setResetTarget(null)}
          onSubmit={async (password) => {
            try {
              await updateUser.mutateAsync({ id: resetTarget.id, password })
              toast.success(`Password reset for ${resetTarget.email}`)
              setResetTarget(null)
            } catch (err: unknown) {
              toast.error(apiErrorMessage(err, 'Could not reset the password'))
            }
          }}
          pending={updateUser.isPending}
        />
      )}
    </div>
  )
}

function ResetPasswordDialog({
  user,
  onClose,
  onSubmit,
  pending,
}: {
  user: ManagedUser
  onClose: () => void
  onSubmit: (password: string) => void
  pending: boolean
}) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  return (
    <Dialog
      title="Reset password"
      onClose={onClose}
      historyKey="reset-password"
      footer={
        <div className="dialog-actions">
          {error && <span className="dialog-form__error">{error}</span>}
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              form="reset-password-form"
              className="dialog-btn dialog-btn--primary"
              disabled={pending}
            >
              {pending ? 'Saving…' : 'Set password'}
            </button>
          </div>
        </div>
      }
    >
      {/* noValidate: the length is checked on submit and said in the footer,
          like every other dialog, not in the browser's own bubble. */}
      <form
        id="reset-password-form"
        className="dialog-form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          if (password.length < 8) {
            setError('Use at least 8 characters')
            return
          }
          setError(null)
          onSubmit(password)
        }}
      >
        <p className="users-panel__dialog-desc">
          Set a new password for <strong>{user.display_name || user.email}</strong>. Tell them
          out-of-band; they can change it themselves afterwards in Settings → Account.
        </p>
        <label className="dialog-form__field">
          <span>New password</span>
          <input
            type="password"
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              setError(null)
            }}
            minLength={8}
            autoFocus
            autoComplete="new-password"
          />
        </label>
      </form>
    </Dialog>
  )
}
