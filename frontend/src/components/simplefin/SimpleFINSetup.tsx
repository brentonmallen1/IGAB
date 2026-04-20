import { useState } from 'react'
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
      setError(err instanceof Error ? err.message : 'Setup failed')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="sf-setup">
      <p className="sf-setup__desc">
        Paste your SimpleFIN setup token below. You can get one at{' '}
        <a href="https://beta-bridge.simplefin.org" target="_blank" rel="noreferrer">
          beta-bridge.simplefin.org
        </a>
        .
      </p>
      <div style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          className="sf-setup__input"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="SimpleFIN setup token…"
          required
        />
        <button
          type="submit"
          className="sf-setup__btn"
          disabled={setup.isPending}
        >
          {setup.isPending ? 'Connecting…' : 'Connect'}
        </button>
      </div>
      {error && <div className="sf-setup__error">{error}</div>}
    </form>
  )
}
