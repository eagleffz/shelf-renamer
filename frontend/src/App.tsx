import { useEffect, useState } from 'react'
import type {
  BookMetadata,
  PreviewItem,
  RenameItem,
  RenameResponse,
} from './api'
import {
  confirmRename,
  fetchBooks,
  fetchConfig,
  previewRename,
} from './api'
import { BookTable } from './components/BookTable'
import { LibrarySelector } from './components/LibrarySelector'
import { PreviewTable } from './components/PreviewTable'
import { ResultsPane } from './components/ResultsPane'
import './index.css'

type Phase = 'browse' | 'preview' | 'results'

const TEMPLATE_VARS = [
  '{title}', '{author}', '{author_lf}', '{authors}',
  '{year}', '{series}', '{series_index}', '{series_index_tag}', '{narrator}',
]

export default function App() {
  const [phase, setPhase] = useState<Phase>('browse')
  const [template, setTemplate] = useState('{author_lf}/{series}/{series_index_tag} - {title}')
  const [libraryId, setLibraryId] = useState('')
  const [books, setBooks] = useState<BookMetadata[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [previewItems, setPreviewItems] = useState<PreviewItem[]>([])
  const [renameResponse, setRenameResponse] = useState<RenameResponse | null>(null)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [showVarHelp, setShowVarHelp] = useState(false)

  useEffect(() => {
    fetchConfig().then((cfg) => setTemplate(cfg.default_template)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!libraryId) return
    setLoading(true)
    setSelected(new Set())
    fetchBooks(libraryId)
      .then(setBooks)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [libraryId])

  function toggleBook(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleAll() {
    setSelected((prev) =>
      prev.size === books.length ? new Set() : new Set(books.map((b) => b.id))
    )
  }

  async function handlePreview() {
    if (!selected.size) return
    setWorking(true)
    setError('')
    try {
      const items = [...selected].map((id) => {
        const book = books.find((b) => b.id === id)!
        return { book_id: id, library_id: book.library_id }
      })
      const result = await previewRename(template, items)
      setPreviewItems(result)
      setPhase('preview')
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setWorking(false)
    }
  }

  async function handleConfirm() {
    setWorking(true)
    setError('')
    try {
      const items: RenameItem[] = previewItems
        .filter((p) => !p.no_change && !p.conflict)
        .map((p) => ({
          book_id: p.book_id,
          library_id: p.library_id,
          current_path: p.current_path,
        }))
      const result = await confirmRename(template, items)
      setRenameResponse(result)
      setPhase('results')
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setWorking(false)
    }
  }

  function handleReset() {
    setPhase('browse')
    setSelected(new Set())
    setPreviewItems([])
    setRenameResponse(null)
    setError('')
    if (libraryId) {
      setLoading(true)
      fetchBooks(libraryId)
        .then(setBooks)
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false))
    }
  }

  const renameableCount = previewItems.filter((p) => !p.no_change && !p.conflict).length

  return (
    <div className="app">
      <header className="navbar">
        <div className="navbar-left">
          <h1 className="app-title">shelf-renamer</h1>
          <LibrarySelector selectedId={libraryId} onChange={setLibraryId} />
        </div>
        <div className="navbar-right">
          <div className="template-wrap">
            <input
              className="template-input"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder="e.g. {author}/{series}/{title} ({year})"
              disabled={phase !== 'browse'}
            />
            <button
              className="btn-icon"
              onClick={() => setShowVarHelp((v) => !v)}
              title="Available variables"
            >
              ?
            </button>
            {showVarHelp && (
              <div className="var-popover">
                {TEMPLATE_VARS.map((v) => (
                  <code
                    key={v}
                    onClick={() => {
                      setTemplate((t) => t + v)
                      setShowVarHelp(false)
                    }}
                    className="var-chip"
                  >
                    {v}
                  </code>
                ))}
              </div>
            )}
          </div>
          {phase === 'browse' && (
            <button
              className="btn btn-primary"
              disabled={!selected.size || working}
              onClick={handlePreview}
            >
              {working ? 'Loading…' : `Preview (${selected.size})`}
            </button>
          )}
          {phase === 'preview' && (
            <>
              <button className="btn btn-secondary" onClick={() => setPhase('browse')}>
                Back
              </button>
              <button
                className="btn btn-danger"
                disabled={!renameableCount || working}
                onClick={handleConfirm}
              >
                {working ? 'Renaming…' : `Rename ${renameableCount} book(s)`}
              </button>
            </>
          )}
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="main">
        {phase === 'browse' && (
          <BookTable
            books={books}
            selected={selected}
            onToggle={toggleBook}
            onSelectAll={toggleAll}
            loading={loading}
          />
        )}
        {phase === 'preview' && <PreviewTable items={previewItems} />}
        {phase === 'results' && renameResponse && (
          <ResultsPane response={renameResponse} onReset={handleReset} />
        )}
      </main>
    </div>
  )
}
