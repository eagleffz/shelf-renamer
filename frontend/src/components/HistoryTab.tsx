import { useEffect, useState } from 'react'
import type { Operation } from '../api'
import { fetchOperations } from '../api'

export function HistoryTab({ libraryId }: { libraryId: string }) {
  const [items, setItems] = useState<Operation[] | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    fetchOperations(libraryId)
      .then((rows) => {
        if (active) {
          setItems(rows)
          setError('')
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message)
      })
    return () => {
      active = false
    }
  }, [libraryId, revision])
  return (
    <section>
      <div className="workflow-heading">
        <div>
          <h2>Operation history</h2>
          <p>
            The latest 500 operations. Pending entries may have been
            interrupted: inspect both paths before attempting recovery.
          </p>
        </div>
        <button
          className="btn btn-secondary"
          onClick={() => setRevision((n) => n + 1)}
        >
          Refresh history
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {!items ? (
        <p role="status">Loading history…</p>
      ) : !items.length ? (
        <p className="empty-state">No rename operations recorded yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="book-table">
            <thead>
              <tr>
                <th>Date (UTC)</th>
                <th>Status</th>
                <th>Previous path</th>
                <th>New path</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.created_at}</td>
                  <td>{item.status}</td>
                  <td className="monospace">{item.old_path}</td>
                  <td className="monospace">{item.new_path}</td>
                  <td>
                    {item.error ||
                      (item.status === 'pending'
                        ? 'Check both paths before retrying; the move may have completed.'
                        : '—')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
