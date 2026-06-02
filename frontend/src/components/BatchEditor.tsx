import { useRef, useState } from 'react'
import type { BookMetadata } from '../api'
import { batchUpdateSeries } from '../api'

interface Props {
  books: BookMetadata[]
  loading: boolean
}

interface Row {
  book_id: string
  series_id: string | null
  series_name: string
  title: string
  published_year: string | null
  abs_path: string
  abs_library_root: string
  sequence: string
  originalSequence: string
  inSeries: boolean
}

type SortCol = 'title' | 'year' | 'sequence'
type SortDir = 'asc' | 'desc'

function seqString(index: number | null): string {
  if (index === null) return ''
  return index === Math.floor(index) ? String(Math.floor(index)) : String(index)
}

// Strip trailing " #N" or " #N.N" that ABS sometimes embeds in the series name field
function normalizeSeriesName(s: string): string {
  return s.trim().replace(/\s*#\d+(\.\d+)?\s*$/, '').trim()
}

function relPath(abs_path: string, abs_library_root: string): string {
  if (abs_path.startsWith(abs_library_root)) {
    return abs_path.slice(abs_library_root.length).replace(/^\//, '')
  }
  return abs_path
}

function seqSortVal(s: string): number {
  const n = parseFloat(s)
  return isNaN(n) ? Infinity : n
}

export function BatchEditor({ books, loading }: Props) {
  const seriesMap = books.filter((b) => b.series).reduce<Record<string, number>>((acc, b) => {
    const key = normalizeSeriesName(b.series!)
    if (key) acc[key] = (acc[key] ?? 0) + 1
    return acc
  }, {})
  const seriesList = Object.entries(seriesMap)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name))

  const [selectedSeries, setSelectedSeries] = useState('')
  const [rows, setRows] = useState<Row[]>([])
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<{ ok: number; fail: number } | null>(null)
  const [sortCol, setSortCol] = useState<SortCol | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const dragIndexRef = useRef<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)

  function selectSeries(name: string) {
    setSelectedSeries(name)
    setSaveResult(null)
    setSortCol(null)
    const nameLower = name.toLowerCase()
    // Sort: series books with number first, series books without number next, other books last
    const sorted = [...books].sort((a, b) => {
      const aInSeries = normalizeSeriesName(a.series ?? '').toLowerCase() === nameLower
      const bInSeries = normalizeSeriesName(b.series ?? '').toLowerCase() === nameLower
      if (aInSeries !== bInSeries) return aInSeries ? -1 : 1
      if (aInSeries && bInSeries) {
        if (a.series_index !== null && b.series_index !== null) return a.series_index - b.series_index
        if (a.series_index !== null) return -1
        if (b.series_index !== null) return 1
      }
      return a.title.localeCompare(b.title)
    })
    setRows(sorted.map((b) => {
      const inSeries = normalizeSeriesName(b.series ?? '').toLowerCase() === nameLower
      return {
        book_id: b.id,
        // Use null ID so ABS looks up/creates by clean name, not by stale per-book ID
        series_id: null,
        series_name: name,  // always the normalized clean name
        title: b.title,
        published_year: b.published_year,
        abs_path: b.abs_path,
        abs_library_root: b.abs_library_root,
        sequence: inSeries ? seqString(b.series_index) : '',
        originalSequence: inSeries ? seqString(b.series_index) : '',
        inSeries,
      }
    }))
  }

  function handleSort(col: SortCol) {
    const dir = sortCol === col && sortDir === 'asc' ? 'desc' : 'asc'
    setSortCol(col)
    setSortDir(dir)
    setRows((prev) => [...prev].sort((a, b) => {
      let cmp = 0
      if (col === 'title') cmp = a.title.localeCompare(b.title)
      else if (col === 'year') cmp = (a.published_year ?? '').localeCompare(b.published_year ?? '')
      else if (col === 'sequence') cmp = seqSortVal(a.sequence) - seqSortVal(b.sequence)
      return dir === 'asc' ? cmp : -cmp
    }))
  }

  function sortIcon(col: SortCol) {
    if (sortCol !== col) return <span className="sort-icon sort-inactive">⇅</span>
    return <span className="sort-icon">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  function updateSequence(i: number, value: string) {
    setRows((prev) => prev.map((r, idx) => idx === i ? { ...r, sequence: value } : r))
  }

  function autoNumber() {
    let n = 0
    setRows((prev) => prev.map((r) => r.inSeries ? { ...r, sequence: String(++n) } : r))
  }

  function handleDragStart(e: React.DragEvent, i: number) {
    dragIndexRef.current = i
    e.dataTransfer.effectAllowed = 'move'
  }

  function handleDragOver(e: React.DragEvent, i: number) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOver(i)
  }

  function handleDrop(e: React.DragEvent, i: number) {
    e.preventDefault()
    const from = dragIndexRef.current
    if (from === null || from === i) { setDragOver(null); return }
    setRows((prev) => {
      const next = [...prev]
      const [item] = next.splice(from, 1)
      next.splice(i, 0, item)
      return next
    })
    dragIndexRef.current = null
    setDragOver(null)
  }

  function handleDragEnd() {
    dragIndexRef.current = null
    setDragOver(null)
  }

  async function handleSave() {
    const changed = rows.filter((r) => r.sequence.trim() !== r.originalSequence)
    if (!changed.length) return
    setSaving(true)
    setSaveResult(null)
    try {
      const results = await batchUpdateSeries(changed.map((r) => ({
        book_id: r.book_id,
        series_id: r.series_id,
        series_name: r.series_name,
        sequence: r.sequence.trim(),
      })))
      const ok = results.filter((r) => r.success).length
      const fail = results.length - ok
      setSaveResult({ ok, fail })
      if (ok > 0) {
        setRows((prev) => prev.map((r) => {
          const res = results.find((x) => x.book_id === r.book_id)
          return res?.success ? { ...r, originalSequence: r.sequence.trim() } : r
        }))
      }
    } catch {
      setSaveResult({ ok: 0, fail: changed.length })
    } finally {
      setSaving(false)
    }
  }

  const changedCount = rows.filter((r) => r.sequence.trim() !== r.originalSequence).length

  if (loading) return <p className="loading">Loading books…</p>

  return (
    <div className="batch-editor">
      <div className="batch-toolbar">
        <select
          className="series-select"
          value={selectedSeries}
          onChange={(e) => selectSeries(e.target.value)}
        >
          <option value="">— Select a series —</option>
          {seriesList.map(({ name, count }) => (
            <option key={name} value={name}>{name} ({count})</option>
          ))}
        </select>

        {rows.length > 0 && (
          <>
            <button className="btn btn-secondary" onClick={autoNumber} disabled={saving}>
              Auto-number
            </button>
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={saving || !changedCount}
            >
              {saving ? 'Saving…' : `Save ${changedCount || ''} change${changedCount !== 1 ? 's' : ''}`}
            </button>
          </>
        )}

        {saveResult && (
          <span className={`batch-save-result ${saveResult.fail > 0 ? 'result-error' : 'result-ok'}`}>
            {saveResult.ok > 0 && `✓ ${saveResult.ok} saved`}
            {saveResult.fail > 0 && ` ✗ ${saveResult.fail} failed`}
          </span>
        )}
      </div>

      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="book-table">
            <thead>
              <tr>
                <th style={{ width: 28 }}></th>
                <th className="sortable-th" onClick={() => handleSort('sequence')}>
                  # {sortIcon('sequence')}
                </th>
                <th style={{ width: 72 }}>Current</th>
                <th className="sortable-th" onClick={() => handleSort('title')}>
                  Title {sortIcon('title')}
                </th>
                <th className="sortable-th" onClick={() => handleSort('year')}>
                  Year {sortIcon('year')}
                </th>
                <th>Path</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const changed = row.sequence.trim() !== row.originalSequence
                const prevInSeries = i > 0 && rows[i - 1].inSeries
                const showDivider = !row.inSeries && prevInSeries
                return (
                  <>
                    {showDivider && (
                      <tr key={`div-${row.book_id}`} className="series-divider-row">
                        <td colSpan={6}>— other books in library —</td>
                      </tr>
                    )}
                  <tr
                    key={row.book_id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, i)}
                    onDragOver={(e) => handleDragOver(e, i)}
                    onDrop={(e) => handleDrop(e, i)}
                    onDragEnd={handleDragEnd}
                    className={`${dragOver === i ? 'drag-over' : ''}${!row.inSeries ? ' row-other' : ''}`}
                    style={{ opacity: dragIndexRef.current === i ? 0.4 : 1 }}
                  >
                    <td className="drag-handle" title="Drag to reorder">⠿</td>
                    <td>
                      <input
                        className={`seq-input${changed ? ' seq-changed' : ''}`}
                        value={row.sequence}
                        onChange={(e) => updateSequence(i, e.target.value)}
                        placeholder="—"
                      />
                    </td>
                    <td className="seq-original">
                      {row.originalSequence || <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </td>
                    <td>{row.title}</td>
                    <td>{row.published_year ?? '—'}</td>
                    <td className="monospace" style={{ fontSize: 11 }}>
                      {relPath(row.abs_path, row.abs_library_root)}
                    </td>
                  </tr>
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {!rows.length && selectedSeries && (
        <p className="loading">No books found for this series.</p>
      )}
    </div>
  )
}
