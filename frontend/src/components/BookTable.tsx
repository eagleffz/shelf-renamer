import type { BookMetadata } from '../api'

interface Props {
  books: BookMetadata[]
  selected: Set<string>
  renamedIds: Set<string>
  alreadyCorrectIds: Set<string>
  absUrl: string
  onToggle: (id: string) => void
  onSelectAll: () => void
  loading: boolean
}

function ExternalLinkIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
      <path d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5z"/>
      <path d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5z"/>
    </svg>
  )
}

export function BookTable({ books, selected, renamedIds, alreadyCorrectIds, absUrl, onToggle, onSelectAll, loading }: Props) {
  if (loading) return <p className="loading">Loading books…</p>
  if (!books.length) return null

  const allSelected = books.length > 0 && selected.size === books.length

  return (
    <div className="table-wrap">
      <table className="book-table">
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                checked={allSelected}
                onChange={onSelectAll}
                title="Select all"
              />
            </th>
            <th>Type</th>
            <th>Current name</th>
            <th>Title</th>
            <th>Author</th>
            <th>Year</th>
            <th>Series</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {books.map((book) => {
            const itemName = book.abs_path.split('/').at(-1) ?? book.abs_path
            const wasRenamed = renamedIds.has(book.id)
            const isCorrect = alreadyCorrectIds.has(book.id)
            return (
              <tr
                key={book.id}
                className={selected.has(book.id) ? 'selected' : ''}
                onClick={() => onToggle(book.id)}
              >
                <td onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.has(book.id)}
                    onChange={() => onToggle(book.id)}
                  />
                </td>
                <td>
                  <span className={`badge ${book.is_file ? 'badge-file' : 'badge-folder'}`}>
                    {book.is_file ? book.file_extension.replace('.', '').toUpperCase() : 'folder'}
                  </span>
                  {(wasRenamed || isCorrect) && (
                    <span
                      className="badge badge-renamed"
                      title={wasRenamed ? 'Previously renamed by shelf-renamer' : 'Already matches the template'}
                    >
                      ✓
                    </span>
                  )}
                </td>
                <td className="monospace">{itemName}</td>
                <td>{book.title}</td>
                <td>{book.authors.map((a) => a.name).join(', ')}</td>
                <td>{book.published_year ?? '—'}</td>
                <td>
                  {book.series
                    ? `${book.series}${book.series_index != null ? ` #${book.series_index}` : ''}`
                    : '—'}
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <a
                    className="btn-abs-link"
                    href={`${absUrl}/item/${book.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Open in Audiobookshelf"
                  >
                    <ExternalLinkIcon />
                  </a>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
