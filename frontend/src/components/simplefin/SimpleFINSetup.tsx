import { useState } from 'react'
import axios from 'axios'
import { AlertTriangle, Check, Copy, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useCurrentUser } from '../../api/auth'
import { useSetupSimpleFIN, useSimpleFINConfig } from '../../api/simplefin'
import './SimpleFINSetup.css'

interface Props {
  onDone: () => void
}

/**
 * Bank sync needs a server-side encryption key. When it is missing, this panel
 * stands in for the token form — the point is that no token gets pasted, since
 * SimpleFIN setup tokens are single-use and a server that cannot store the
 * result would spend one to tell you so.
 */
function ConfigProblemPanel({
  problem,
  command,
  isAdmin,
  onRecheck,
  rechecking,
}: {
  problem: string
  command: string
  isAdmin: boolean
  onRecheck: () => void
  rechecking: boolean
}) {
  const [copied, setCopied] = useState(false)

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Over plain http on a LAN address the clipboard API is unavailable —
      // the command is selectable text either way.
      toast.error('Could not copy — select the command and copy it manually')
    }
  }

  return (
    <div className="sf-blocked">
      <div className="sf-blocked__head">
        <AlertTriangle size={16} className="sf-blocked__icon" aria-hidden />
        <span className="sf-blocked__title">Bank sync isn’t ready on this server</span>
      </div>
      <p className="sf-blocked__problem">{problem}</p>

      {isAdmin ? (
        <>
          <ol className="sf-blocked__steps">
            <li>
              Generate a key:
              <span className="sf-blocked__cmdrow">
                <code className="sf-blocked__cmd">{command}</code>
                <button
                  type="button"
                  className="sf-blocked__copy"
                  onClick={copyCommand}
                  title="Copy command"
                  aria-label="Copy command"
                >
                  {copied ? <Check size={13} /> : <Copy size={13} />}
                </button>
              </span>
            </li>
            <li>
              Set <code>SIMPLEFIN_ENCRYPTION_KEY</code> to that value wherever this server’s
              environment is configured. On Unraid it is on the container’s edit page with{' '}
              <strong>Advanced View</strong> turned on — the field is hidden until then. With
              Docker Compose it goes in <code>.env</code>.
            </li>
            <li>Restart IGAB, then check again.</li>
          </ol>
          <p className="sf-blocked__note">
            Keep that key somewhere safe. Connections saved with it cannot be read by any other
            key — if it is lost or changed, every SimpleFIN connection has to be removed and set
            up again.
          </p>
        </>
      ) : (
        <p className="sf-blocked__note">
          Ask whoever runs this server to set <code>SIMPLEFIN_ENCRYPTION_KEY</code>, then check
          again.
        </p>
      )}

      <button type="button" className="sf-blocked__recheck" onClick={onRecheck} disabled={rechecking}>
        <RefreshCw size={13} className={rechecking ? 'sf-blocked__spin' : undefined} />
        {rechecking ? 'Checking…' : 'Check again'}
      </button>
    </div>
  )
}

export function SimpleFINSetup({ onDone }: Props) {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const setup = useSetupSimpleFIN()
  const config = useSimpleFINConfig()
  const { data: me } = useCurrentUser()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await setup.mutateAsync(token.trim())
      setToken('')
      onDone()
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail ?? err.message)
        // 503 is the server saying it cannot store credentials. Re-asking
        // swaps this form for the panel that explains it, so the next attempt
        // is a fix rather than another token.
        if (err.response?.status === 503) config.refetch()
      } else {
        setError(err instanceof Error ? err.message : 'Setup failed')
      }
    }
  }

  if (config.isLoading) {
    return <p className="sf-setup__note">Checking bank sync configuration…</p>
  }

  if (config.data && !config.data.configured) {
    return (
      <ConfigProblemPanel
        problem={config.data.problem ?? 'Bank sync is not configured on this server.'}
        command={config.data.generate_key_command}
        isAdmin={!!me?.is_admin}
        onRecheck={() => config.refetch()}
        rechecking={config.isFetching}
      />
    )
  }

  return (
    <form onSubmit={handleSubmit} className="sf-setup">
      <ol className="sf-setup__steps">
        <li>
          Go to{' '}
          <a href="https://beta-bridge.simplefin.org/simplefin/create" target="_blank" rel="noreferrer">
            beta-bridge.simplefin.org/simplefin/create
          </a>
        </li>
        <li>Click <strong>+New Token</strong> (or similar) to generate a <strong>Setup Token</strong></li>
        <li>Copy the token — it starts with <code>aHR0c</code> or similar base64 characters</li>
        <li>Paste it below and click Connect</li>
      </ol>
      <p className="sf-setup__note">
        This is a one-time token — not your SimpleFIN password or any persistent API key.
        Tokens expire quickly, so paste and connect within a minute or two of generating it.
      </p>
      <div style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          className="sf-setup__input"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Paste setup token here…"
          required
        />
        <button
          type="submit"
          className="sf-setup__btn"
          disabled={setup.isPending || !token.trim()}
        >
          {setup.isPending ? 'Connecting…' : 'Connect'}
        </button>
      </div>
      {error && (
        <div className="sf-setup__error">
          <AlertTriangle size={14} aria-hidden />
          <span>{error}</span>
        </div>
      )}
    </form>
  )
}

/**
 * The same panel, for callers that show connections rather than the setup
 * form: a key lost or rotated after setup breaks every sync, and the
 * connection list on its own never says why. Renders nothing when the server
 * is configured.
 */
export function SimpleFINConfigNotice() {
  const config = useSimpleFINConfig()
  const { data: me } = useCurrentUser()

  if (!config.data || config.data.configured) return null

  return (
    <ConfigProblemPanel
      problem={config.data.problem ?? 'Bank sync is not configured on this server.'}
      command={config.data.generate_key_command}
      isAdmin={!!me?.is_admin}
      onRecheck={() => config.refetch()}
      rechecking={config.isFetching}
    />
  )
}
