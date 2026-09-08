import { useState } from 'react'

interface Props {
  onLogin: (password: string) => Promise<void>
}

export function LoginPage({ onLogin }: Props) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await onLogin(password)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-overlay">
      <div className="login-card">
        <h1 className="app-title login-title">shelf-renamer</h1>
        <form className="login-form" onSubmit={handleSubmit}>
          <input
            className="login-input"
            type="password"
            aria-label="Password"
            autoComplete="current-password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
          />
          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="btn btn-primary login-btn"
            disabled={!password || loading}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
