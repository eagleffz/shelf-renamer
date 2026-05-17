import { useState } from 'react'
import type { BookMetadata, PreviewItem } from '../api'

interface Props {
  items: PreviewItem[]
  books: BookMetadata[]
  overrides: Record<string, Record<string, string>>
  onOverrideChange: (bookId: string, field: string, value: string) => void
}

function FolderIcon() {
  return (
    <svg className="path-icon path-icon-folder" viewBox="0 0 16 16" fill="currentColor">
      <path d="M1.5 3A1.5 1.5 0 000 4.5v8A1.5 1.5 0 001.5 14h13a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H7.621a1.5 1.5 0 01-1.06-.44L5.5 3H1.5z" />
    </svg>
  )
}

function FileIcon() {
  return (
    <svg className="path-icon path-icon-file" viewBox="0 0 16 16" fill="currentColor">
      <path d="M4 0a2 2 0 00-2 2v12a2 2 0 002 2h8a2 2 0 002-2V4.414A2 2 0 0013.414 3L11 .586A2 2 0 009.586 0H4zm4 1.5v3A1.5 1.5 0 009.5 6H13v8a.5.5 0 01-.5.5h-9A.5.5 0 013 14V2a.5.5 0 01.5-.5H8z" />
    </svg>
  )
}

function PathBreadcrumb({ path, variant }: { path: string; variant: 'old' | 'new' }) {
  const parts = path.split('/').filter(Boolean)
  if (!parts.length) return <span className="breadcrumb-empty">—</span>
  const dirs = parts.slice(0, -1)
  const file = parts[parts.length - 1]
  return (
    <span className={`path-crumb path-crumb-${variant}`}>
      {dirs.map((dir, i) => (
        <span key={i} className="path-dir-pill">
          <FolderIcon />
          <span className="path-dir-label">{dir}</span>
        </span>
      ))}
      {dirs.length > 0 && <span className="path-arrow">›</span>}
      <span className="path-file">
        <FileIcon />
        <span className="path-file-label">{file}</span>
      </span>
    </span>
  )
}

const OVERRIDE_FIELDS: { key: string; label: string; small?: boolean }[] = [
  { key: 'author',       label: 'Author' },
  { key: 'title',        label: 'Title' },
  { key: 'series',       label: 'Series' },
  { key: 'series_index', label: '#', small: true },
  { key: 'year',         label: 'Year', small: true },
  { key: 'narrator',     label: 'Narrator' },
]

function getBookDefault(book: BookMetadata, key: string): string {
  switch (key) {
    case 'author':       return book.authors[0]?.name ?? ''
    case 'title':        return book.title
    case 'series':       return book.series ?? ''
    case 'series_index': return book.series_index != null ? String(book.series_index) : ''
    case 'year':         return book.published_year ?? ''
    case 'narrator':     return book.narrator ?? ''
    default:             return ''
  }
}

function OverrideEditor({
  book,
  overrides,
  onCommit,
}: {
  book: BookMetadata
  overrides: Record<string, string>
  onCommit: (field: string, value: string) => void
}) {
  const [local, setLocal] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const f of OVERRIDE_FIELDS) {
      init[f.key] = overrides[f.key] ?? getBookDefault(book, f.key)
    }
    return init
  })

  return (
    <div className="override-grid">
      {OVERRIDE_FIELDS.map((f) => (
        <label key={f.key} className={`override-field${f.small ? ' override-field-small' : ''}`}>
          <span className="override-label">{f.label}</span>
          <input
            className="override-input"
            value={local[f.key]}
            onChange={(e) => setLocal((prev) => ({ ...prev, [f.key]: e.target.value }))}
            onBlur={(e) => {
              const current = overrides[f.key] ?? getBookDefault(book, f.key)
              if (e.target.value !== current) onCommit(f.key, e.target.value)
            }}
          />
        </label>
      ))}
    </div>
  )
}

export function PreviewTable({ items, books, overrides, onOverrideChange }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (!items.length) return null

  const changes = items.filter((i) => !i.no_change)
  const noChange = items.filter((i) => i.no_change)
  const bookMap = Object.fromEntries(books.map((b) => [b.id, b]))

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
              <th></th>
            </tr>
          </thead>
          <tbody>
            {changes.map((item) => {
              const isExpanded = expandedId === item.book_id
              const book = bookMap[item.book_id]
              return (
                <>
                  <tr key={item.book_id} className={item.conflict ? 'conflict' : ''}>
                    <td><PathBreadcrumb path={item.current_name} variant="old" /></td>
                    <td className="arrow">→</td>
                    <td><PathBreadcrumb path={item.proposed_name} variant="new" /></td>
                    <td>
                      {item.conflict
                        ? <span className="badge badge-conflict">Conflict</span>
                        : <span className="badge badge-ok">OK</span>}
                    </td>
                    <td>
                      <button
                        className={`btn-edit${isExpanded ? ' btn-edit-active' : ''}`}
                        title="Override metadata fields"
                        onClick={() => setExpandedId(isExpanded ? null : item.book_id)}
                      >
                        ✎
                      </button>
                    </td>
                  </tr>
                  {isExpanded && book && (
                    <tr key={`${item.book_id}-edit`} className="override-row">
                      <td colSpan={5}>
                        <OverrideEditor
                          book={book}
                          overrides={overrides[item.book_id] ?? {}}
                          onCommit={(field, value) => onOverrideChange(item.book_id, field, value)}
                        />
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      )}
      {noChange.length > 0 && (
        <p className="muted">{noChange.length} book(s) already correctly named — skipped.</p>
      )}
    </div>
  )
}
