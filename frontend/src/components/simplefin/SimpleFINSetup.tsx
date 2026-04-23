import { useState } from 'react'
import axios from 'axios'
import { useSetupSimpleFIN } from '../../api/simplefin'
import './SimpleFINSetup.css'

interface Props {
  onDone: () => void
}

export function SimpleFINSetup({ onDone }: Props) {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const setup = useSetupSimpleFIN()

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
      } else {
        setError(err instanceof Error ? err.message : 'Setup failed')
      }
    }
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
      {error && <div className="sf-setup__error">{error}</div>}
    </form>
  )
}
