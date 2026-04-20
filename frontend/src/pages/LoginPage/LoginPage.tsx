import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLogin } from '../../api/auth'
import './LoginPage.css'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const loginMutation = useLogin()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    try {
      await loginMutation.mutateAsync({ email, password })
      navigate('/budget', { replace: true })
    } catch {
      // error shown via loginMutation.error
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-card__logo">
          <div className="login-card__logo-text">IGAB</div>
          <div className="login-card__subtitle">I've Got A Budget</div>
        </div>

        <form className="login-card__form" onSubmit={handleSubmit}>
          <div className="login-card__field">
            <label className="login-card__label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              className="login-card__input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@example.com"
              required
              autoComplete="email"
            />
          </div>

          <div className="login-card__field">
            <label className="login-card__label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="login-card__input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>

          {loginMutation.isError && (
            <div className="login-card__error">Invalid email or password.</div>
          )}

          <button
            type="submit"
            className="login-card__submit"
            disabled={loginMutation.isPending}
          >
            {loginMutation.isPending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
