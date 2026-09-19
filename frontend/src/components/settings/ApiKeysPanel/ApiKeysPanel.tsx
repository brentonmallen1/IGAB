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
import {
  KEY_PLACEHOLDER,
  MCP_CLIENTS,
  mcpClient,
  mcpConnectSnippet,
  mcpEndpoint,
  type McpClientKind,
} from './mcpConnect'
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
      <ConnectSection />

      <div className="settings-subsection">
        <div className="settings-subsection__title">Keys</div>
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

/**
 * How to connect, kept where the keys are.
 *
 * The command used to exist only in the dialog that shows a new key, which is
 * the one moment someone does not need reminding. The question arrives later
 * — a new laptop, a second client, a key already sitting in a config file —
 * and by then the dialog is unreachable and the key is unprintable.
 */
function ConnectSection() {
  const [kind, setKind] = useState<McpClientKind>('claude-code')
  const origin = window.location.origin
  const endpoint = mcpEndpoint(origin)
  const client = mcpClient(kind)
  const snippet = mcpConnectSnippet(kind, origin)

  return (
    <div className="settings-subsection">
      <div className="settings-subsection__title">How to connect</div>
      <div className="settings-row__desc">
        IGAB serves a read-only MCP endpoint, so an assistant can answer questions about a budget —
        what a category has left, what a month came to — without a screenshot. Make a key below,
        then point a client at it. It is an ordinary bearer token, so anything that speaks MCP
        works, not only what is listed here.
      </div>

      <div className="mcp-connect">
        <div className="mcp-connect__field">
          <span className="mcp-connect__label">Endpoint</span>
          <div className="mcp-connect__value">
            <code className="mcp-connect__code">{endpoint}</code>
            <CopyButton text={endpoint} label="Copy endpoint" />
          </div>
        </div>

        <label className="mcp-connect__field">
          <span className="mcp-connect__label">Client</span>
          <select
            className="settings-select"
            value={kind}
            onChange={(e) => setKind(e.target.value as McpClientKind)}
          >
            {MCP_CLIENTS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <div className="mcp-connect__field">
          <span className="mcp-connect__label">{client.fieldLabel}</span>
          <div className="mcp-connect__value">
            <code className="mcp-connect__code">{snippet}</code>
            <CopyButton text={snippet} label={client.copyLabel} />
          </div>
        </div>

        <div className="settings-row__desc">
          Any MCP client works — it is an ordinary bearer token, sent as{' '}
          <code>Authorization: Bearer …</code>. A key is shown once, when you make it; put it where{' '}
          <code>{KEY_PLACEHOLDER}</code> is.
        </div>
      </div>
    </div>
  )
}

/**
 * Copying is the only thing anyone does with these strings, and the clipboard
 * is not always there: on a LAN address over plain HTTP the page is not a
 * secure context and the API is simply undefined. Every caller needs the same
 * fallback, so it lives here rather than beside each button.
 */
function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      toast.error('Could not copy — select the text instead.')
    }
  }

  return (
    <button className="settings-btn settings-btn--secondary" onClick={copy} aria-label={label}>
      {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}{' '}
      {label}
    </button>
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
  const [kind, setKind] = useState<McpClientKind>('claude-code')
  const origin = window.location.origin
  const client = mcpClient(kind)
  const snippet = mcpConnectSnippet(kind, origin, issued.key)

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
        <CopyButton text={issued.key} label="Copy key" />

        <label className="dialog-form__field">
          <span>Client</span>
          <select
            className="settings-select"
            value={kind}
            onChange={(e) => setKind(e.target.value as McpClientKind)}
          >
            {MCP_CLIENTS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <label className="dialog-form__field">
          <span>{client.fieldLabel}</span>
          <textarea
            readOnly
            rows={snippet.split('\n').length + 1}
            value={snippet}
            onFocus={(e) => e.currentTarget.select()}
          />
          <span className="dialog-form__hint">
            Any MCP client works — it is an ordinary bearer token. Point yours at{' '}
            <code>{mcpEndpoint(origin)}</code> with this key in an Authorization header. The same
            instructions are in Settings afterwards; this key is not.
          </span>
        </label>
        <CopyButton text={snippet} label={client.copyLabel} />
      </div>
    </Dialog>
  )
}
