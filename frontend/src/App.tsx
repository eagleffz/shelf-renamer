import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  AppConfig,
  BookMetadata,
  PreviewItem,
  RenameItem,
  RenameResponse,
} from './api'
import {
  cleanupEmptyDirs,
  clearAuthToken,
  confirmRename,
  fetchBooks,
  fetchConfig,
  fetchHistory,
  getAuthToken,
  login,
  previewRename,
  setAuthToken,
  setUnauthorizedHandler,
} from './api'
import { BookTable } from './components/BookTable'
import { LibrarySelector } from './components/LibrarySelector'
import { LoginPage } from './components/LoginPage'
import { PreviewTable } from './components/PreviewTable'
import { ResultsPane } from './components/ResultsPane'
import './index.css'

type Phase = 'browse' | 'preview' | 'results'

const TEMPLATE_VARS = [
  '{title}', '{author}', '{author_lf}', '{authors}',
  '{year}', '{series}', '{series_index}', '{series_index_tag}', '{narrator}',
]

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [phase, setPhase] = useState<Phase>('browse')
  const [template, setTemplate] = useState('{author_lf}/{series}/{series_index_tag} - {title}')
  const [libraryId, setLibraryId] = useState('')
  const [books, setBooks] = useState<BookMetadata[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [renamedIds, setRenamedIds] = useState<Set<string>>(new Set())

  // books that already match the current template (computed in background)
  const [alreadyCorrectIds, setAlreadyCorrectIds] = useState<Set<string>>(new Set())

  // filter: show only books that don't match the template
  const [filterActive, setFilterActive] = useState(false)
  const [filterIds, setFilterIds] = useState<Set<string> | null>(null)
  const [filterLoading, setFilterLoading] = useState(false)

  // per-book field overrides for preview
  const [overrides, setOverrides] = useState<Record<string, Record<string, string>>>({})

  const [cleanupWorking, setCleanupWorking] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<string | null>(null)

  const [previewItems, setPreviewItems] = useState<PreviewItem[]>([])
  const [renameResponse, setRenameResponse] = useState<RenameResponse | null>(null)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [showVarHelp, setShowVarHelp] = useState(false)

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthenticated(false))
    fetchConfig().then((cfg) => {
      setConfig(cfg)
      setTemplate(cfg.default_template)
      if (!cfg.auth_required || getAuthToken()) setAuthenticated(true)
    }).catch(() => {})
  }, [])

  function handleSignOut() {
    clearAuthToken()
    setAuthenticated(false)
  }

  useEffect(() => {
    if (!libraryId || !authenticated) return
    setLoading(true)
    setSelected(new Set())
    setFilterActive(false)
    setFilterIds(null)
    Promise.all([fetchBooks(libraryId), fetchHistory(libraryId)])
      .then(([bks, ids]) => {
        setBooks(bks)
        setRenamedIds(new Set(ids))
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [libraryId, authenticated])

  async function handleLogin(password: string) {
    const { token } = await login(password)
    setAuthToken(token)
    setAuthenticated(true)
  }

  const computePreviewAll = useCallback(async () => {
    if (!books.length || !template) return null
    const items = books.map((b) => ({ book_id: b.id, library_id: b.library_id }))
    const result = await previewRename(template, items)
    setAlreadyCorrectIds(new Set(result.filter((r) => r.no_change).map((r) => r.book_id)))
    return result
  }, [books, template])

  // background debounced computation whenever books or template change
  const bgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (bgTimerRef.current) clearTimeout(bgTimerRef.current)
    bgTimerRef.current = setTimeout(() => { computePreviewAll().catch(() => {}) }, 700)
    return () => { if (bgTimerRef.current) clearTimeout(bgTimerRef.current) }
  }, [computePreviewAll])

  async function toggleFilter() {
    if (filterActive) {
      setFilterActive(false)
      setFilterIds(null)
      return
    }
    setFilterLoading(true)
    setFilterActive(true)
    try {
      const result = await computePreviewAll()
      if (result) setFilterIds(new Set(result.filter((r) => !r.no_change).map((r) => r.book_id)))
      else { setFilterActive(false); setFilterIds(null) }
    } catch {
      setFilterActive(false)
      setFilterIds(null)
    } finally {
      setFilterLoading(false)
    }
  }

  async function handleCleanup() {
    setCleanupWorking(true)
    setCleanupResult(null)
    try {
      const { removed } = await cleanupEmptyDirs()
      setCleanupResult(
        removed.length
          ? `Removed ${removed.length} empty folder${removed.length !== 1 ? 's' : ''}`
          : 'No empty folders found'
      )
    } catch {
      setCleanupResult('Cleanup failed')
    } finally {
      setCleanupWorking(false)
    }
  }

  function handleTemplateChange(value: string) {
    setTemplate(value)
    if (filterActive) {
      setFilterActive(false)
      setFilterIds(null)
    }
  }

  const displayedBooks = filterActive && filterIds !== null
    ? books.filter((b) => filterIds.has(b.id))
    : books

  function toggleBook(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleAll() {
    setSelected((prev) =>
      prev.size === displayedBooks.length
        ? new Set()
        : new Set(displayedBooks.map((b) => b.id))
    )
  }

  async function handlePreview() {
    if (!selected.size) return
    setWorking(true)
    setError('')
    setOverrides({})
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

  async function handleOverrideChange(bookId: string, field: string, value: string) {
    const bookOverrides = { ...overrides[bookId], [field]: value }
    const nextOverrides = { ...overrides, [bookId]: bookOverrides }
    setOverrides(nextOverrides)

    const item = previewItems.find((p) => p.book_id === bookId)
    if (!item) return
    try {
      const result = await previewRename(template, [{
        book_id: bookId,
        library_id: item.library_id,
        overrides: bookOverrides,
      }])
      if (result[0]) {
        setPreviewItems((prev) => prev.map((p) => p.book_id === bookId ? result[0] : p))
      }
    } catch {}
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
          overrides: overrides[p.book_id],
        }))
      const result = await confirmRename(template, items)
      setRenameResponse(result)
      setPhase('results')
      const newIds = result.results.filter((r) => r.success).map((r) => r.book_id)
      setRenamedIds((prev) => new Set([...prev, ...newIds]))
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
    setOverrides({})
    setError('')
    if (libraryId) {
      setLoading(true)
      Promise.all([fetchBooks(libraryId), fetchHistory(libraryId)])
        .then(([bks, ids]) => { setBooks(bks); setRenamedIds(new Set(ids)) })
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false))
    }
  }

  if (!config) return null
  if (config.auth_required && !authenticated) return <LoginPage onLogin={handleLogin} />

  const renameableCount = previewItems.filter((p) => !p.no_change && !p.conflict).length

  return (
    <div className="app">
      <header className="navbar">
        <div className="navbar-left">
          <h1 className="app-title">
            shelf-renamer
            <span className="app-version">{config.version}</span>
          </h1>
          <LibrarySelector selectedId={libraryId} onChange={setLibraryId} />
          {config.auth_required && (
            <button className="btn-signout" onClick={handleSignOut} title="Sign out / re-login">
              Sign out
            </button>
          )}
        </div>
        <div className="navbar-right">
          <div className="template-wrap">
            <input
              className="template-input"
              value={template}
              onChange={(e) => handleTemplateChange(e.target.value)}
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
                    onClick={() => { setTemplate((t) => t + v); setShowVarHelp(false) }}
                    className="var-chip"
                  >
                    {v}
                  </code>
                ))}
              </div>
            )}
          </div>
          {phase === 'browse' && (
            <>
              <button
                className={`btn btn-secondary${filterActive ? ' btn-active' : ''}`}
                disabled={!books.length || filterLoading}
                onClick={toggleFilter}
                title="Show only books whose path doesn't match the current template"
              >
                {filterLoading
                  ? 'Filtering…'
                  : filterActive && filterIds !== null
                    ? `Changes only (${filterIds.size})`
                    : 'Show changes'}
              </button>
              <button
                className="btn btn-secondary"
                disabled={cleanupWorking}
                onClick={handleCleanup}
                title="Remove empty folders under the media root"
              >
                {cleanupWorking ? 'Cleaning…' : 'Clean empty folders'}
              </button>
              <button
                className="btn btn-primary"
                disabled={!selected.size || working}
                onClick={handlePreview}
              >
                {working ? 'Loading…' : `Preview (${selected.size})`}
              </button>
            </>
          )}
          {phase === 'preview' && (
            <>
              <button className="btn btn-secondary" onClick={() => setPhase('browse')}>Back</button>
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
      {cleanupResult && (
        <div className="info-banner" onClick={() => setCleanupResult(null)}>
          {cleanupResult} <span className="info-banner-dismiss">✕</span>
        </div>
      )}

      <main className="main">
        {phase === 'browse' && (
          <BookTable
            books={displayedBooks}
            selected={selected}
            renamedIds={renamedIds}
            alreadyCorrectIds={alreadyCorrectIds}
            onToggle={toggleBook}
            onSelectAll={toggleAll}
            loading={loading}
          />
        )}
        {phase === 'preview' && (
          <PreviewTable
            items={previewItems}
            books={books}
            overrides={overrides}
            onOverrideChange={handleOverrideChange}
          />
        )}
        {phase === 'results' && renameResponse && (
          <ResultsPane response={renameResponse} onReset={handleReset} />
        )}
      </main>
    </div>
  )
}
