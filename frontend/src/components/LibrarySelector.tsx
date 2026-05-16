import { useEffect, useState } from 'react'
import type { Library } from '../api'
import { fetchLibraries } from '../api'

interface Props {
  selectedId: string
  onChange: (id: string) => void
}

export function LibrarySelector({ selectedId, onChange }: Props) {
  const [libraries, setLibraries] = useState<Library[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    fetchLibraries()
      .then(setLibraries)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <span style={{ color: 'var(--color-error)' }}>Failed to load libraries: {error}</span>

  return (
    <select
      value={selectedId}
      onChange={(e) => onChange(e.target.value)}
      className="select"
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
