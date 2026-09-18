import { Check, Copy, KeyRound, Trash2 } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'

import { apiErrorMessage } from '../../../api/client'
import {
  useApiKeys,
  useCreateApiKey,
  useRevokeApiKey,
  type ApiKeyCreated,
} from '../../../api/apiKeys'
import { useBudgets } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { Dialog } from '../../common/Dialog/Dialog'
import './ApiKeysPanel.css'

/**
 * Read-only keys for connecting an assistant.
 *
 * The app's own credentials do not fit: a session token lasts 30 minutes,
 * and the refresh token behind it can mint full write access to everything
 * its owner has. A key is the narrow thing — read-only, scoped to named
 * budgets, revocable by itself.
 *
 * It is a plain bearer token on purpose, so it is vendor-agnostic: anything
 * that speaks MCP and can set a header will work, not just one client.
 */
export function ApiKeysPanel() {
  const { data: keys, isLoading } = useApiKeys()
  const { data: budgets } = useBudgets()
  const revoke = useRevokeApiKey()
  const { formatDateTime } = useFormatters()
  const [creating, setCreating] = useState(false)
  const [issued, setIssued] = useState<ApiKeyCreated | null>(null)

  const rows = keys ?? []

  return (
    <div className="bkp-panel">
      <div className="settings-subsection">
        <div className="settings-subsection__title">Assistant access</div>
        <div className="settings-row">
          <div>
            <div className="settings-row__label">Read-only API keys</div>
            <div className="settings-row__desc">
              Let an assistant answer questions about a budget — what a category has left, what a
              month came to — without a screenshot. A key can only read, only the budgets you name,
              and can be revoked on its own without signing you out anywhere.
            </div>
          </div>
          <button
            className="settings-btn settings-btn--primary"
            onClick={() => setCreating(true)}
            disabled={!budgets?.length}
          >
            <KeyRound size={14} aria-hidden="true" /> New key
          </button>
        </div>

        <div className="bkp-files">
          {isLoading ? (
            <div className="bkp-files__empty">Loading…</div>
          ) : rows.length === 0 ? (
            <div className="bkp-files__empty">
              No keys yet. “New key” makes one and shows it once.
            </div>
          ) : (
            <table className="bkp-table surface surface--sunken">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Key</th>
                  <th scope="col">Last used</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((key) => (
                  <tr key={key.id} className={key.revoked_at ? 'api-key--revoked' : undefined}>
                    <td className="bkp-table__name">
                      <span className="bkp-table__name-inner">
                        <KeyRound size={13} aria-hidden="true" />
                        {key.name}
                        {key.revoked_at && <span className="api-key__badge">revoked</span>}
                      </span>
                    </td>
                    <td className="tabular">{key.prefix}…</td>
                    <td>{key.last_used_at ? formatDateTime(key.last_used_at) : 'Never'}</td>
                    <td className="bkp-table__action">
                      {!key.revoked_at && (
                        <button
                          className="settings-btn settings-btn--danger"
                          onClick={() =>
                            revoke
                              .mutateAsync(key.id)
                              .then(() => toast.success('Key revoked'))
                              .catch((err) =>
                                toast.error(apiErrorMessage(err, 'Could not revoke the key'))
                              )
                          }
                          aria-label={`Revoke ${key.name}`}
                        >
                          <Trash2 size={13} aria-hidden="true" /> Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {creating && (
        <NewKeyDialog
          onClose={() => setCreating(false)}
          onCreated={(key) => {
            setCreating(false)
            setIssued(key)
          }}
        />
      )}
      {issued && <IssuedKeyDialog issued={issued} onClose={() => setIssued(null)} />}
    </div>
  )
}

function NewKeyDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (key: ApiKeyCreated) => void
}) {
  const { data: budgets } = useBudgets()
  const create = useCreateApiKey()
  const [name, setName] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const ready = name.trim().length > 0 && selected.length > 0

  async function submit() {
    setError(null)
    try {
      onCreated(await create.mutateAsync({ name: name.trim(), budget_ids: selected }))
    } catch (err) {
      setError(apiErrorMessage(err, 'The key could not be created'))
    }
  }

  return (
    <Dialog
      title="New API key"
      historyKey="api-key-new"
      onClose={onClose}
      footer={
        <div className="dialog-buttons">
          {/* Enabled, with the reason in the footer when it cannot go
              through — the dialog standard: a disabled button that will not
              say why is the thing this repo stopped shipping. */}
          {error && <span className="dialog-form__error">{error}</span>}
          <button className="dialog-btn dialog-btn--secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="dialog-btn dialog-btn--primary"
            onClick={() => (ready ? submit() : setError('Give the key a name and pick a budget.'))}
            disabled={create.isPending}
          >
            {create.isPending ? 'Creating…' : 'Create key'}
          </button>
        </div>
      }
    >
      <div className="dialog-form">
        <label className="dialog-form__field">
          <span>Name</span>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Claude on the laptop"
            maxLength={100}
          />
          <span className="dialog-form__hint">
            Only ever for you — it says which key a row in the list is.
          </span>
        </label>

        <div className="dialog-form__field">
          <span>Budgets this key may read</span>
          {(budgets ?? []).map((budget) => (
            <label key={budget.id} className="dialog-form__field--inline">
              <input
                type="checkbox"
                checked={selected.includes(budget.id)}
                onChange={(e) =>
                  setSelected((prev) =>
                    e.target.checked ? [...prev, budget.id] : prev.filter((id) => id !== budget.id)
                  )
                }
              />
              <span>{budget.name}</span>
            </label>
          ))}
          <span className="dialog-form__hint">
            The key can read these and nothing else. Naming more than one means the assistant has to
            say which it means.
          </span>
        </div>
      </div>
    </Dialog>
  )
}

function IssuedKeyDialog({ issued, onClose }: { issued: ApiKeyCreated; onClose: () => void }) {
  const [copied, setCopied] = useState<'key' | 'command' | null>(null)
  const command = `claude mcp add --transport http igab ${window.location.origin}/api/v1/mcp --header "Authorization: Bearer ${issued.key}"`

  async function copy(what: 'key' | 'command', text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(what)
    } catch {
      // Over plain HTTP on a LAN address the clipboard API is unavailable —
      // the field is selectable, so say nothing and let them copy by hand.
      toast.error('Could not copy — select the text instead.')
    }
  }

  return (
    <Dialog
      title="Your new key"
      historyKey="api-key-issued"
      onClose={onClose}
      footer={
        <div className="dialog-buttons">
          <button className="dialog-btn dialog-btn--primary" onClick={onClose}>
            Done
          </button>
        </div>
      }
    >
      <div className="dialog-form">
        <p className="dialog-form__hint api-key__warning">
          Copy it now. The server keeps only a hash, the same way it does for a password, so this is
          the one time it can be shown. If you lose it, revoke this key and make another.
        </p>

        <label className="dialog-form__field">
          <span>Key</span>
          <input readOnly value={issued.key} onFocus={(e) => e.currentTarget.select()} />
        </label>
        <button
          className="settings-btn settings-btn--secondary"
          onClick={() => copy('key', issued.key)}
        >
          {copied === 'key' ? <Check size={13} /> : <Copy size={13} />} Copy key
        </button>

        <label className="dialog-form__field">
          <span>Connect Claude Code</span>
          <textarea readOnly rows={3} value={command} onFocus={(e) => e.currentTarget.select()} />
          <span className="dialog-form__hint">
            Any MCP client works — it is an ordinary bearer token. Point yours at{' '}
            <code>{window.location.origin}/api/v1/mcp</code> with this key in an Authorization
            header.
          </span>
        </label>
        <button
          className="settings-btn settings-btn--secondary"
          onClick={() => copy('command', command)}
        >
          {copied === 'command' ? <Check size={13} /> : <Copy size={13} />} Copy command
        </button>
      </div>
    </Dialog>
  )
}
