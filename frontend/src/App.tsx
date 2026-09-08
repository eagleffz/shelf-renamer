import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  AppConfig,
  BookMetadata,
  PreviewItem,
  RenameResponse,
} from './api'
import {
  cleanupEmptyDirs,
  clearAuthToken,
  clearHistory,
  confirmRename,
  fetchBooks,
  fetchConfig,
  fetchHistory,
  fetchSession,
  login,
  logout,
  previewRename,
  scanLibrary,
  setUnauthorizedHandler,
} from './api'
import { BatchEditor } from './components/BatchEditor'
import { BookTable } from './components/BookTable'
import { ConfigTab } from './components/ConfigTab'
import { HistoryTab } from './components/HistoryTab'
import { LibrarySelector } from './components/LibrarySelector'
import { LoginPage } from './components/LoginPage'
import { PreviewTable } from './components/PreviewTable'
import { ResultsPane } from './components/ResultsPane'
import {
  readPreference,
  savePreference,
  toggleVisibleSelection,
} from './selection'
import './index.css'

type Tab = 'library' | 'batch' | 'history' | 'config'
const VARIABLES = [
  'title',
  'author',
  'author_lf',
  'authors',
  'year',
  'series',
  'series_index',
  'series_index_tag',
  'narrator',
]
const PRESETS = [
  [
    'Author / Series / Title',
    '{author_lf}/{series}/{series_index_tag} - {title}',
  ],
  ['Author – Title (Year)', '{author} - {title} ({year})'],
  ['Title only', '{title}'],
]

export default function App() {
  const [attempt, setAttempt] = useState(0)
  return <Session key={attempt} retry={() => setAttempt((n) => n + 1)} />
}

function Session({ retry }: { retry: () => void }) {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    try {
      clearAuthToken()
    } catch {
      /* Legacy storage may be unavailable. */
    }
    setUnauthorizedHandler(() => {
      if (active) setAuthenticated(false)
    })
    fetchConfig()
      .then(async (cfg) => {
        let valid = !cfg.auth_required
        if (cfg.auth_required) {
          try {
            await fetchSession()
            valid = true
          } catch {
            valid = false
          }
        }
        if (active) {
          setConfig(cfg)
          setAuthenticated(valid)
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message)
      })
    return () => {
      active = false
      setUnauthorizedHandler(() => {})
    }
  }, [])
  if (error)
    return (
      <main className="empty-state" role="alert">
        <h1>Could not connect to shelf-renamer</h1>
        <p>{error}</p>
        <button className="btn btn-primary" onClick={retry}>
          Retry connection
        </button>
      </main>
    )
  if (!config)
    return (
      <p className="loading" role="status">
        Connecting to shelf-renamer…
      </p>
    )
  if (!authenticated)
    return (
      <LoginPage
        onLogin={async (password) => {
          await login(password)
          setAuthenticated(true)
        }}
      />
    )
  return (
    <Application
      config={config}
      signOut={async () => {
        await logout()
        setAuthenticated(false)
      }}
    />
  )
}

function Application({
  config,
  signOut,
}: {
  config: AppConfig
  signOut: () => Promise<void>
}) {
  const [libraryId, setLibraryId] = useState(() =>
    readPreference('shelf-library', ''),
  )
  const [tab, setTab] = useState<Tab>('library')
  const [locked, setLocked] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const allowLeave = () =>
    !dirty || window.confirm('Discard unsaved series changes?')
  return (
    <div className="app">
      <header className="navbar">
        <div className="navbar-left">
          <h1 className="app-title">
            shelf-renamer <span className="app-version">{config.version}</span>
          </h1>
          <LibrarySelector
            selectedId={libraryId}
            disabled={locked}
            onChange={(id) => {
              if (!allowLeave()) return
              setDirty(false)
              setLibraryId(id)
              savePreference('shelf-library', id)
            }}
          />
        </div>
        {config.auth_required && (
          <button
            className="btn btn-secondary"
            disabled={locked}
            onClick={() => {
              if (allowLeave())
                signOut().catch((e: Error) => setError(e.message))
            }}
          >
            Sign out
          </button>
        )}
      </header>
      <nav className="tab-bar" aria-label="Application sections">
        {(['library', 'batch', 'history', 'config'] as Tab[]).map((t) => (
          <button
            key={t}
            className={`tab-btn${tab === t ? ' tab-active' : ''}`}
            aria-current={tab === t ? 'page' : undefined}
            disabled={locked && tab !== t}
            onClick={() => setTab(t)}
          >
            {
              {
                library: 'Library',
                batch: 'Batch Editor',
                history: 'History',
                config: 'Config',
              }[t]
            }
          </button>
        ))}
      </nav>
      {error && (
        <div role="alert" className="error-banner">
          {error}
        </div>
      )}
      <main className="main">
        {tab === 'config' && <ConfigTab config={config} />}
        {!libraryId && tab !== 'config' && (
          <div className="empty-state">
            <h2>Choose an audiobook library</h2>
            <p>
              Select a library above, then choose a naming template and preview
              your changes.
            </p>
          </div>
        )}
        {libraryId && (
          <LibraryWorkspace
            key={libraryId}
            libraryId={libraryId}
            config={config}
            tab={tab}
            setLocked={setLocked}
            setDirty={setDirty}
          />
        )}
      </main>
    </div>
  )
}

function LibraryWorkspace({
  libraryId,
  config,
  tab,
  setLocked,
  setDirty,
}: {
  libraryId: string
  config: AppConfig
  tab: Tab
  setLocked: (v: boolean) => void
  setDirty: (v: boolean) => void
}) {
  const preferenceKey = `shelf-template:${libraryId}`
  const [template, setTemplate] = useState(() =>
    readPreference(preferenceKey, config.default_template),
  )
  const [savedTemplate, setSavedTemplate] = useState(() =>
    readPreference(preferenceKey, ''),
  )
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState<{
    revision: number
    books: BookMetadata[]
    history: Set<string>
    error: string
  } | null>(null)
  const books = useMemo(() => data?.books ?? [], [data])
  const renamedIds = useMemo(() => data?.history ?? new Set<string>(), [data])
  const loading = data?.revision !== revision
  const [phase, setPhase] = useState<'browse' | 'preview' | 'results'>('browse')
  const [filter, setFilter] = useState<'all' | 'needs' | 'matches'>('needs')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [status, setStatus] = useState<{
    key: string
    items: PreviewItem[]
    error: string
  } | null>(null)
  const [previewItems, setPreviewItems] = useState<PreviewItem[]>([])
  const [overrides, setOverrides] = useState<
    Record<string, Record<string, string>>
  >({})
  const [response, setResponse] = useState<RenameResponse | null>(null)
  const [working, setWorking] = useState(false)
  const [pendingPreview, setPendingPreview] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [cleanupPaths, setCleanupPaths] = useState<string[] | null>(null)
  const overrideRequest = useRef(0)
  const overrideValues = useRef(overrides)
  const statusKey = `${revision}:${template}`
  const bookMap = useMemo(
    () => new Map(books.map((book) => [book.id, book])),
    [books],
  )
  const ready = !loading && status?.key === statusKey && !status.error
  const correctIds = useMemo(
    () =>
      new Set(
        ready
          ? status.items
              .filter((p) => p.no_change)
              .map((p) => p.book_id)
          : [],
      ),
    [ready, status],
  )

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      fetchBooks(libraryId, revision > 0, controller.signal),
      fetchHistory(libraryId),
    ])
      .then(([bks, history]) => {
        if (!controller.signal.aborted)
          setData({
            revision,
            books: bks,
            history: new Set(history),
            error: '',
          })
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted)
          setData({ revision, books: [], history: new Set(), error: e.message })
      })
    return () => controller.abort()
  }, [libraryId, revision])

  useEffect(() => {
    if (loading || !books.length) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      previewRename(
        template,
        books.map((b) => ({ book_id: b.id, library_id: libraryId })),
        controller.signal,
      )
        .then((items) => {
          if (!controller.signal.aborted)
            setStatus({ key: statusKey, items, error: '' })
        })
        .catch((e: Error) => {
          if (!controller.signal.aborted)
            setStatus({ key: statusKey, items: [], error: e.message })
        })
    }, 500)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [books, template, libraryId, loading, statusKey])

  useEffect(() => {
    setLocked(working || phase === 'preview')
    return () => setLocked(false)
  }, [working, phase, setLocked])
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (working) e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [working])

  const displayed = useMemo(
    () =>
      books.filter(
        (b) =>
          (filter === 'all' ||
            !ready ||
            (filter === 'matches'
              ? correctIds.has(b.id)
              : !correctIds.has(b.id))) &&
          `${b.title} ${b.authors.map((a) => a.name).join(' ')} ${b.series ?? ''}`
            .toLowerCase()
            .includes(query.toLowerCase().trim()),
      ),
    [books, filter, ready, correctIds, query],
  )
  const visibleIds = displayed.map((b) => b.id)
  const visibleSet = new Set(visibleIds)
  const hiddenCount = [...selected].filter((id) => !visibleSet.has(id)).length
  const toggleBook = useCallback(
    (id: string) =>
      setSelected((prev) => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      }),
    [],
  )

  function refresh() {
    setSelected(new Set())
    setRevision((n) => n + 1)
  }
  async function run(task: () => Promise<void>) {
    setWorking(true)
    setError('')
    setNotice('')
    try {
      await task()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setWorking(false)
    }
  }
  async function preview(ids = [...selected]) {
    await run(async () => {
      overrideValues.current = {}
      setOverrides({})
      const items = await previewRename(
        template,
        ids.map((id) => ({ book_id: id, library_id: libraryId })),
      )
      setPreviewItems(items)
      setPhase('preview')
    })
  }
  async function changeOverride(bookId: string, field: string, value: string) {
    const next = {
      ...overrideValues.current,
      [bookId]: { ...overrideValues.current[bookId], [field]: value },
    }
    overrideValues.current = next
    setOverrides(next)
    await refreshOverridePreview(next)
  }
  async function refreshOverridePreview(next = overrideValues.current) {
    const requestId = ++overrideRequest.current
    setPendingPreview(true)
    setError('')
    try {
      const items = await previewRename(
        template,
        previewItems.map((p) => ({
          book_id: p.book_id,
          library_id: p.library_id,
          overrides: next[p.book_id],
        })),
      )
      if (requestId === overrideRequest.current) {
        setPreviewItems(items)
        setPendingPreview(false)
      }
    } catch (e) {
      if (requestId === overrideRequest.current) setError((e as Error).message)
    }
  }
  async function confirm() {
    await run(async () => {
      const items = previewItems
        .filter((p) => !p.no_change && !p.conflict)
        .map((p) => ({
          book_id: p.book_id,
          library_id: p.library_id,
          current_path: p.current_path,
          preview_token: p.preview_token,
          overrides: overrideValues.current[p.book_id],
        }))
      const result = await confirmRename(template, items)
      setResponse(result)
      setPhase('results')
      setRevision((n) => n + 1)
    })
  }
  const renameable = previewItems.filter(
    (p) => !p.no_change && !p.conflict,
  ).length

  return (
    <>
      <section hidden={tab !== 'library'} aria-label="Rename library">
        {error && (
          <div className="error-banner" role="alert">
            {error}
            {phase === 'preview' && (
              <button
                className="btn btn-secondary"
                disabled={working}
                onClick={() => refreshOverridePreview()}
              >
                Retry preview
              </button>
            )}
            <button className="btn btn-secondary" onClick={() => setError('')}>
              Dismiss
            </button>
          </div>
        )}
        {notice && (
          <div className="info-banner" role="status">
            {notice}
            <button className="btn btn-secondary" onClick={() => setNotice('')}>
              Dismiss
            </button>
          </div>
        )}
        {phase === 'browse' && (
          <>
            <div className="workflow-heading">
              <div>
                <h2>Rename your audiobooks</h2>
                <p>
                  Choose a template, select books, and review every destination
                  before applying changes.
                </p>
              </div>
              <details className="maintenance">
                <summary>Library maintenance</summary>
                <div className="maintenance-actions">
                  <button
                    className="btn btn-secondary"
                    disabled={working}
                    onClick={() =>
                      run(async () => {
                        await scanLibrary(libraryId)
                        setNotice(
                          'Rescan requested. Refresh after Audiobookshelf finishes scanning.',
                        )
                      })
                    }
                  >
                    Rescan library
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={working}
                    onClick={() =>
                      run(async () => {
                        const result = await cleanupEmptyDirs(libraryId)
                        setCleanupPaths(result.candidates)
                        if (!result.candidates.length)
                          setNotice('No empty folders found in this library.')
                      })
                    }
                  >
                    Review empty folders
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={working}
                    onClick={() => {
                      if (
                        window.confirm(
                          'Clear previously-renamed badges for this library? The operation log will be kept.',
                        )
                      )
                        run(async () => {
                          await clearHistory(libraryId)
                          refresh()
                          setNotice(
                            'Previously-renamed badges cleared. The operation log is preserved.',
                          )
                        })
                    }}
                  >
                    Clear history badges
                  </button>
                </div>
              </details>
            </div>
            {!!cleanupPaths?.length && (
              <div
                className="review-panel"
                role="region"
                aria-label="Review folder cleanup"
              >
                <h3>Remove {cleanupPaths.length} empty folders?</h3>
                <p>
                  Only the folders listed below in this library will be removed.
                </p>
                <ul className="path-list">
                  {cleanupPaths.map((path) => (
                    <li key={path}>{path}</li>
                  ))}
                </ul>
                <button
                  className="btn btn-danger"
                  disabled={working}
                  onClick={() =>
                    run(async () => {
                      const result = await cleanupEmptyDirs(
                        libraryId,
                        cleanupPaths,
                      )
                      setCleanupPaths(null)
                      setNotice(
                        `Removed ${result.removed.length} empty folders.`,
                      )
                      if (result.errors.length)
                        setError(result.errors.join('; '))
                    })
                  }
                >
                  Remove listed folders
                </button>
                <button
                  className="btn btn-secondary"
                  disabled={working}
                  onClick={() => setCleanupPaths(null)}
                >
                  Cancel
                </button>
              </div>
            )}
            <div className="template-panel">
              <label htmlFor="naming-template">Naming template</label>
              <input
                id="naming-template"
                className="template-input"
                value={template}
                maxLength={1000}
                onChange={(e) => setTemplate(e.target.value)}
                disabled={working}
                aria-describedby="template-help"
              />
              <div className="template-presets">
                <label>
                  Preset{' '}
                  <select
                    aria-label="Naming preset"
                    value=""
                    disabled={working}
                    onChange={(e) => setTemplate(e.target.value)}
                  >
                    <option value="">Choose a preset…</option>
                    {PRESETS.map(([name, value]) => (
                      <option key={name} value={value}>
                        {name}
                      </option>
                    ))}
                    {savedTemplate && (
                      <option value={savedTemplate}>
                        Saved for this library
                      </option>
                    )}
                  </select>
                </label>
                <button
                  className="btn btn-secondary"
                  disabled={!ready || working}
                  onClick={() => {
                    savePreference(preferenceKey, template)
                    setSavedTemplate(template)
                    setNotice(
                      'Template saved for this library in this browser.',
                    )
                  }}
                >
                  Save template
                </button>
              </div>
              <details>
                <summary>Available variables</summary>
                <div className="variable-list">
                  {VARIABLES.map((name) => (
                    <button
                      key={name}
                      className="var-chip"
                      disabled={working}
                      onClick={() => setTemplate((t) => t + `{${name}}`)}
                    >{`{${name}}`}</button>
                  ))}
                </div>
              </details>
              <p id="template-help">
                Use / for folders. Empty metadata segments are skipped. File
                extensions are preserved.
              </p>
              {status?.key === statusKey && status.error && (
                <p role="alert" className="result-error">
                  {status.error}
                </p>
              )}
              {books.length > 0 &&
                !ready &&
                !(status?.key === statusKey && status.error) && (
                  <p role="status">Checking template…</p>
                )}
              {ready && status.items[0] && (
                <p className="example-path">
                  Example:{' '}
                  <code>
                    {status.items[0].proposed_name || status.items[0].error}
                  </code>
                  {status.items[0].warnings.length > 0 && (
                    <span> · {status.items[0].warnings.join(', ')}</span>
                  )}
                </p>
              )}
            </div>
            <div className="library-toolbar">
              <label className="search-label">
                Search
                <input
                  className="title-filter-input"
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Title, author, or series"
                />
              </label>
              <div className="filter-buttons" aria-label="Naming status">
                {(['all', 'needs', 'matches'] as const).map((mode) => (
                  <button
                    key={mode}
                    className={`btn btn-secondary${filter === mode ? ' btn-active' : ''}`}
                    aria-pressed={filter === mode}
                    onClick={() => setFilter(mode)}
                    disabled={mode !== 'all' && !ready}
                  >
                    {mode === 'all'
                      ? `All (${books.length})`
                      : mode === 'needs'
                        ? `Needs changes (${ready ? books.length - correctIds.size : '…'})`
                        : `Matches (${ready ? correctIds.size : '…'})`}
                  </button>
                ))}
              </div>
              <button
                className="btn btn-secondary"
                disabled={working || loading}
                onClick={refresh}
              >
                {loading ? 'Refreshing…' : 'Refresh from ABS'}
              </button>
            </div>
            {data?.error && (
              <div role="alert" className="empty-state">
                <h3>Could not load this library</h3>
                <p>{data.error}</p>
                <button className="btn btn-primary" onClick={refresh}>
                  Retry
                </button>
              </div>
            )}
            <BookTable
              books={displayed}
              selected={selected}
              renamedIds={renamedIds}
              alreadyCorrectIds={correctIds}
              absUrl={config.abs_url}
              onToggle={toggleBook}
              onSelectAll={() =>
                setSelected((prev) => toggleVisibleSelection(prev, visibleIds))
              }
              loading={loading}
              emptyMessage={
                books.length
                  ? 'No books match these filters. Try All or clear your search.'
                  : 'This library has no books. Check Audiobookshelf, then refresh.'
              }
            />
            <div className="selection-bar">
              <span role="status">
                {selected.size} selected
                {hiddenCount > 0 ? ` · ${hiddenCount} hidden by filters` : ''}
              </span>
              <button
                className="btn btn-secondary"
                disabled={!selected.size || working}
                onClick={() => setSelected(new Set())}
              >
                Clear selection
              </button>
              <button
                className="btn btn-primary"
                disabled={!selected.size || working || loading || !ready}
                onClick={() => preview()}
              >
                {working ? 'Preparing…' : `Preview ${selected.size} books`}
              </button>
            </div>
          </>
        )}
        {phase === 'preview' && (
          <>
            <div className="workflow-heading">
              <div>
                <h2>Review changes</h2>
                <p>
                  {renameable} ready ·{' '}
                  {previewItems.filter((p) => p.conflict).length} blocked ·{' '}
                  {
                    previewItems.filter((p) => p.no_change && !p.conflict)
                      .length
                  }{' '}
                  unchanged
                </p>
                <p>
                  Blocked books are excluded. Overrides change filenames only;
                  they do not edit ABS metadata.
                </p>
              </div>
            </div>
            <PreviewTable
              items={previewItems}
              bookMap={bookMap}
              overrides={overrides}
              onOverrideChange={changeOverride}
              disabled={working}
            />
            <div className="selection-bar">
              <button
                className="btn btn-secondary"
                disabled={working}
                onClick={() => {
                  overrideRequest.current++
                  setPendingPreview(false)
                  setPhase('browse')
                  setError('')
                }}
              >
                Back to selection
              </button>
              <span role="status">
                {pendingPreview
                  ? 'Waiting for a valid updated preview…'
                  : working
                    ? 'Renaming… Keep this page open.'
                    : 'Review the paths above before continuing.'}
              </span>
              <button
                className="btn btn-danger"
                disabled={!renameable || working || pendingPreview}
                onClick={confirm}
              >
                {working ? 'Renaming…' : `Rename ${renameable} books`}
              </button>
            </div>
          </>
        )}
        {phase === 'results' && response && (
          <ResultsPane
            response={response}
            onReset={() => {
              setPhase('browse')
              setSelected(new Set())
              setError('')
            }}
            onRetry={() =>
              preview(
                response.results
                  .filter((r) => !r.success)
                  .map((r) => r.book_id),
              )
            }
            onScan={() =>
              run(async () => {
                await scanLibrary(libraryId)
                setNotice(
                  'Rescan requested. Refresh after ABS finishes scanning.',
                )
                setResponse((prev) =>
                  prev
                    ? { ...prev, scan_errors: [], scan_triggered: true }
                    : prev,
                )
              })
            }
            working={working}
          />
        )}
      </section>
      <section hidden={tab !== 'batch'} aria-label="Edit series">
        <BatchEditor
          key={libraryId}
          books={books}
          loading={loading}
          libraryId={libraryId}
          onSaved={() => setRevision((n) => n + 1)}
          onDirtyChange={setDirty}
          onWorkingChange={setLocked}
        />
      </section>
      {tab === 'history' && (
        <HistoryTab key={`${libraryId}:${revision}`} libraryId={libraryId} />
      )}
    </>
  )
}
