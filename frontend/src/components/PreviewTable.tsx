import type { PreviewItem } from '../api'

interface Props {
  items: PreviewItem[]
}

export function PreviewTable({ items }: Props) {
  if (!items.length) return null

  const changes = items.filter((i) => !i.no_change)
  const noChange = items.filter((i) => i.no_change)

  return (
    <div className="table-wrap">
      {changes.length === 0 && (
        <p className="info">All selected books already match the template. Nothing to rename.</p>
      )}
      {changes.length > 0 && (
        <table className="preview-table">
          <thead>
            <tr>
              <th>Current name</th>
              <th></th>
              <th>Proposed name</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {changes.map((item) => (
              <tr key={item.book_id} className={item.conflict ? 'conflict' : ''}>
                <td className="monospace old-name">{item.current_name}</td>
                <td className="arrow">→</td>
                <td className="monospace new-name">{item.proposed_name}</td>
                <td>
                  {item.conflict ? (
                    <span className="badge badge-conflict">Conflict</span>
                  ) : (
                    <span className="badge badge-ok">OK</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {noChange.length > 0 && (
        <p className="muted">{noChange.length} book(s) already correctly named — skipped.</p>
      )}
    </div>
  )
}
