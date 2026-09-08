import { useEffect, useState } from 'react'
import type { Library } from '../api'
import { fetchLibraries } from '../api'

interface Props {
  selectedId: string
  onChange: (id: string) => void
  disabled?: boolean
}

export function LibrarySelector({ selectedId, onChange, disabled }: Props) {
  const [libraries, setLibraries] = useState<Library[]>([])
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    fetchLibraries()
      .then((items) => {
        if (active) {
          setLibraries(items)
          setError('')
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message)
      })
    return () => {
      active = false
    }
  }, [attempt])

  if (error)
    return (
      <span role="alert" style={{ color: 'var(--color-error)' }}>
        Failed to load libraries: {error}{' '}
        <button
          className="btn btn-secondary"
          onClick={() => setAttempt((n) => n + 1)}
        >
          Retry libraries
        </button>
      </span>
    )

  return (
    <select
      value={selectedId}
      onChange={(e) => onChange(e.target.value)}
      className="select"
      aria-label="Audiobook library"
      disabled={disabled}
    >
      <option value="">— Select library —</option>
      {libraries.map((lib) => (
        <option key={lib.id} value={lib.id}>
          {lib.name}
        </option>
      ))}
    </select>
  )
}
