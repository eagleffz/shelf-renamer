import type { PreviewItem } from '../api'

interface Props {
  items: PreviewItem[]
}

function PathBreadcrumb({ path, className }: { path: string; className?: string }) {
  const parts = path.split('/')
  return (
    <span className={`breadcrumb ${className ?? ''}`}>
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 && <span className="breadcrumb-sep">/</span>}
          <span className={i === parts.length - 1 ? 'breadcrumb-leaf' : 'breadcrumb-dir'}>
            {part}
          </span>
        </span>
      ))}
    </span>
  )
}

export function PreviewTable({ items }: Props) {
  if (!items.length) return null

  const changes = items.filter((i) => !i.no_change)
  const noChange = items.filter((i) => i.no_change)

  return (
    <div className="preview-wrap">
      {changes.length === 0 && (
        <p className="info">All selected books already match the template. Nothing to rename.</p>
      )}
      {changes.length > 0 && (
        <table className="preview-table">
          <thead>
            <tr>
              <th>Current path</th>
              <th></th>
              <th>Proposed path</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {changes.map((item) => (
              <tr key={item.book_id} className={item.conflict ? 'conflict' : ''}>
                <td><PathBreadcrumb path={item.current_name} className="old-name" /></td>
                <td className="arrow">→</td>
                <td><PathBreadcrumb path={item.proposed_name} className="new-name" /></td>
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
