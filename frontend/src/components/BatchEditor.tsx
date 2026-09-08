import { useEffect, useMemo, useState } from 'react'
import type { BookMetadata } from '../api'
import { batchUpdateSeries } from '../api'

interface Props {
  books: BookMetadata[]
  loading: boolean
  libraryId: string
  onSaved: () => void
  onDirtyChange: (dirty: boolean) => void
  onWorkingChange: (working: boolean) => void
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
  error?: string
}

type SortCol = 'title' | 'year' | 'sequence'
type SortDir = 'asc' | 'desc'

function seqString(index: number | null): string {
  if (index === null) return ''
  return index === Math.floor(index) ? String(Math.floor(index)) : String(index)
}

function normalizeSeriesName(s: string): string {
  return s
    .trim()
    .replace(/\s*#\d+(\.\d+)?\s*$/, '')
    .trim()
}

function indexFromName(name: string | null): string {
  if (!name) return ''
  const m = name.match(/#(\d+(?:\.\d+)?)\s*$/)
  return m ? m[1] : ''
}

function resolveSeq(index: number | null, seriesName: string | null): string {
  if (index !== null) return seqString(index)
  return indexFromName(seriesName)
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

export function BatchEditor({
  books,
  loading,
  onSaved,
  onDirtyChange,
  onWorkingChange,
}: Props) {
  const seriesList = useMemo(() => {
    const seriesMap = books
      .filter((b) => b.series)
      .reduce<Record<string, number>>((acc, b) => {
        const key = normalizeSeriesName(b.series!)
        if (key) acc[key] = (acc[key] ?? 0) + 1
        return acc
      }, {})
    return Object.entries(seriesMap)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [books])

  const [selectedSeries, setSelectedSeries] = useState('')
  const [rows, setRows] = useState<Row[]>([])
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<{
    ok: number
    fail: number
  } | null>(null)
  const [sortCol, setSortCol] = useState<SortCol | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const changedCount = rows.filter(
    (r) => r.sequence.trim() !== r.originalSequence,
  ).length
  const invalidSequence = rows.some(
    (r) => r.sequence.trim() && !Number.isFinite(Number(r.sequence)),
  )
  const sequences = rows.map((r) => r.sequence.trim()).filter(Boolean)
  const duplicateSequence =
    new Set(sequences.map(Number)).size !== sequences.length
  useEffect(() => {
    onDirtyChange(changedCount > 0)
    const warn = (e: BeforeUnloadEvent) => {
      if (changedCount || saving) e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [changedCount, saving, onDirtyChange])
  useEffect(() => {
    onWorkingChange(saving)
  }, [saving, onWorkingChange])

  function selectSeries(name: string) {
    if (
      changedCount &&
      !window.confirm(
        'Discard unsaved changes before selecting another series?',
      )
    )
      return
    setSelectedSeries(name)
    setSaveResult(null)
    setSortCol(null)
    const nameLower = name.toLowerCase()
    const filtered = books
      .filter(
        (b) => normalizeSeriesName(b.series ?? '').toLowerCase() === nameLower,
      )
      .sort((a, b) => {
        const ai =
          a.series_index ?? parseFloat(indexFromName(a.series) || 'NaN')
        const bi =
          b.series_index ?? parseFloat(indexFromName(b.series) || 'NaN')
        if (!isNaN(ai) && !isNaN(bi)) return ai - bi
        if (!isNaN(ai)) return -1
        if (!isNaN(bi)) return 1
        return a.title.localeCompare(b.title)
      })
    setRows(
      filtered.map((b) => ({
        book_id: b.id,
        series_id: b.series_id,
        series_name: name,
        title: b.title,
        published_year: b.published_year,
        abs_path: b.abs_path,
        abs_library_root: b.abs_library_root,
        sequence: resolveSeq(b.series_index, b.series),
        originalSequence: resolveSeq(b.series_index, b.series),
      })),
    )
  }

  function handleSort(col: SortCol) {
    const dir = sortCol === col && sortDir === 'asc' ? 'desc' : 'asc'
    setSortCol(col)
    setSortDir(dir)
    setRows((prev) =>
      [...prev].sort((a, b) => {
        let cmp = 0
        if (col === 'title') cmp = a.title.localeCompare(b.title)
        else if (col === 'year')
          cmp = (a.published_year ?? '').localeCompare(b.published_year ?? '')
        else if (col === 'sequence')
          cmp = seqSortVal(a.sequence) - seqSortVal(b.sequence)
        return dir === 'asc' ? cmp : -cmp
      }),
    )
  }

  function sortIcon(col: SortCol) {
    if (sortCol !== col)
      return <span className="sort-icon sort-inactive">⇅</span>
    return <span className="sort-icon">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  function updateSequence(i: number, value: string) {
    setRows((prev) =>
      prev.map((r, idx) => (idx === i ? { ...r, sequence: value } : r)),
    )
  }

  function autoNumber() {
    let n = 0
    setRows((prev) => prev.map((r) => ({ ...r, sequence: String(++n) })))
  }

  async function handleSave() {
    const changed = rows.filter((r) => r.sequence.trim() !== r.originalSequence)
    if (!changed.length || invalidSequence) return
    setSaving(true)
    setSaveResult(null)
    try {
      const results = await batchUpdateSeries(
        changed.map((r) => ({
          book_id: r.book_id,
          series_id: r.series_id,
          series_name: r.series_name,
          sequence: r.sequence.trim(),
        })),
      )
      const ok = results.filter((r) => r.success).length
      const fail = results.length - ok
      setSaveResult({ ok, fail })
      if (ok > 0) {
        const resultMap = new Map(results.map((x) => [x.book_id, x]))
        setRows((prev) =>
          prev.map((r) => {
            const res = resultMap.get(r.book_id)
            return res?.success
              ? {
                  ...r,
                  originalSequence: changed
                    .find((item) => item.book_id === r.book_id)!
                    .sequence.trim(),
                  error: undefined,
                }
              : res
                ? { ...r, error: res.error ?? 'Update failed. Try again.' }
                : r
          }),
        )
        onSaved()
      } else {
        setRows((prev) =>
          prev.map((r) => ({
            ...r,
            error:
              results.find((item) => item.book_id === r.book_id)?.error ??
              r.error,
          })),
        )
      }
    } catch (e) {
      setSaveResult({ ok: 0, fail: changed.length })
      setRows((prev) =>
        prev.map((r) =>
          changed.some((item) => item.book_id === r.book_id)
            ? { ...r, error: (e as Error).message }
            : r,
        ),
      )
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="loading">Loading books…</p>

  return (
    <div className="batch-editor">
      <div className="workflow-heading">
        <div>
          <h2>Edit series order</h2>
          <p>
            These changes update metadata in Audiobookshelf. Unsaved edits are
            kept while switching tabs.
          </p>
        </div>
      </div>
      <div className="batch-toolbar">
        <select
          className="series-select"
          value={selectedSeries}
          aria-label="Series to edit"
          disabled={saving}
          onChange={(e) => selectSeries(e.target.value)}
        >
          <option value="">— Select a series —</option>
          {seriesList.map(({ name, count }) => (
            <option key={name} value={name}>
              {name} ({count})
            </option>
          ))}
        </select>

        {rows.length > 0 && (
          <>
            <button
              className="btn btn-secondary"
              onClick={autoNumber}
              disabled={saving}
            >
              Auto-number
            </button>
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={saving || !changedCount || invalidSequence}
            >
              {saving
                ? 'Saving…'
                : `Save ${changedCount || ''} change${changedCount !== 1 ? 's' : ''}`}
            </button>
          </>
        )}

        {saveResult && (
          <span
            role="status"
            className={`batch-save-result ${saveResult.fail > 0 ? 'result-error' : 'result-ok'}`}
          >
            {saveResult.ok > 0 && `✓ ${saveResult.ok} saved`}
            {saveResult.fail > 0 && ` ✗ ${saveResult.fail} failed`}
          </span>
        )}
      </div>
      {invalidSequence && (
        <p role="alert" className="result-error">
          Use a valid number (including decimals), or leave the sequence empty.
        </p>
      )}
      {duplicateSequence && (
        <p className="metadata-warning">
          Some books have the same sequence. Review the order before saving.
        </p>
      )}
      {!selectedSeries && (
        <p className="empty-state">
          Choose a series to review its order. Sort the table, then use
          Auto-number or edit individual positions.
        </p>
      )}

      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="book-table">
            <thead>
              <tr>
                <th
                  aria-sort={
                    sortCol === 'sequence'
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                >
                  <button
                    className="sort-button"
                    disabled={saving}
                    onClick={() => handleSort('sequence')}
                  >
                    Sequence {sortIcon('sequence')}
                  </button>
                </th>
                <th style={{ width: 72 }}>Current</th>
                <th
                  aria-sort={
                    sortCol === 'title'
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                >
                  <button
                    className="sort-button"
                    disabled={saving}
                    onClick={() => handleSort('title')}
                  >
                    Title {sortIcon('title')}
                  </button>
                </th>
                <th
                  aria-sort={
                    sortCol === 'year'
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                >
                  <button
                    className="sort-button"
                    disabled={saving}
                    onClick={() => handleSort('year')}
                  >
                    Year {sortIcon('year')}
                  </button>
                </th>
                <th>Path</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const changed = row.sequence.trim() !== row.originalSequence
                return (
                  <tr key={row.book_id}>
                    <td>
                      <input
                        className={`seq-input${changed ? ' seq-changed' : ''}`}
                        value={row.sequence}
                        aria-label={`Sequence for ${row.title}`}
                        inputMode="decimal"
                        disabled={saving}
                        aria-invalid={
                          !!row.sequence.trim() &&
                          !Number.isFinite(Number(row.sequence))
                        }
                        onChange={(e) => updateSequence(i, e.target.value)}
                        placeholder="—"
                      />
                    </td>
                    <td className="seq-original">
                      {row.originalSequence || (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                    </td>
                    <td>
                      {row.title}
                      {row.error && (
                        <p role="alert" className="result-error">
                          {row.error}
                        </p>
                      )}
                    </td>
                    <td>{row.published_year ?? '—'}</td>
                    <td className="monospace" style={{ fontSize: 11 }}>
                      {relPath(row.abs_path, row.abs_library_root)}
                    </td>
                  </tr>
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
