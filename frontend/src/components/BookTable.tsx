import type { BookMetadata } from '../api'

interface Props {
  books: BookMetadata[]
  selected: Set<string>
  onToggle: (id: string) => void
  onSelectAll: () => void
  loading: boolean
}

export function BookTable({ books, selected, onToggle, onSelectAll, loading }: Props) {
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
            <th>Folder name</th>
            <th>Title</th>
            <th>Author</th>
            <th>Year</th>
            <th>Series</th>
          </tr>
        </thead>
        <tbody>
          {books.map((book) => {
            const folderName = book.abs_path.split('/').at(-1) ?? book.abs_path
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
                <td className="monospace">{folderName}</td>
                <td>{book.title}</td>
                <td>{book.authors.map((a) => a.name).join(', ')}</td>
                <td>{book.published_year ?? '—'}</td>
                <td>
                  {book.series
                    ? `${book.series}${book.series_index != null ? ` #${book.series_index}` : ''}`
                    : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
