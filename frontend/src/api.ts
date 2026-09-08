export interface Author {
  id: string
  name: string
}

export interface BookMetadata {
  id: string
  library_id: string
  title: string
  authors: Author[]
  series: string | null
  series_id: string | null
  series_index: number | null
  published_year: string | null
  narrator: string | null
  abs_path: string
  abs_library_root: string
  is_file: boolean
  file_extension: string
}

export interface Library {
  id: string
  name: string
  folders: string[]
}

export interface PreviewItem {
  book_id: string
  library_id: string
  current_name: string
  proposed_name: string
  current_path: string
  proposed_path: string
  conflict: boolean
  no_change: boolean
  error: string | null
  warnings: string[]
  preview_token: string
}

export interface RenameItem {
  book_id: string
  library_id: string
  current_path: string
  overrides?: Record<string, string>
  preview_token: string
}

export interface RenameResult {
  book_id: string
  success: boolean
  error: string | null
  old_path: string
  new_path: string
}

export interface RenameResponse {
  results: RenameResult[]
  scan_triggered: boolean
  scan_errors: string[]
}

export interface VolumeMapEntry {
  abs_root: string
  container_root: string
}

export interface AppConfig {
  default_template: string
  auth_required: boolean
  version: string
  abs_url: string
  media_root: string
  volume_map: VolumeMapEntry[]
}

const TOKEN_KEY = 'shelf-renamer-token'

export const clearAuthToken = () => localStorage.removeItem(TOKEN_KEY)

let _onUnauthorized: (() => void) | null = null
export const setUnauthorizedHandler = (fn: () => void) => {
  _onUnauthorized = fn
}

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }

  const res = await fetch(path, { headers, ...options })
  if (!res.ok) {
    if (res.status === 401 && _onUnauthorized) {
      clearAuthToken()
      _onUnauthorized()
    }
    const text = await res.text()
    let message = text || `Request failed (${res.status})`
    try {
      const body = JSON.parse(text)
      message =
        typeof body.detail === 'string'
          ? body.detail
          : Array.isArray(body.detail)
            ? body.detail.map((d: { msg: string }) => d.msg).join('; ')
            : message
    } catch {
      /* Non-JSON upstream error. */
    }
    throw new ApiError(res.status, message)
  }
  return res.json()
}

export const fetchConfig = () => request<AppConfig>('/api/config')
export const fetchSession = () => request('/api/auth/session')
export const logout = () => request('/api/auth/logout', { method: 'POST' })

export const login = (password: string) =>
  request<{ authenticated: boolean }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })

export const fetchLibraries = () => request<Library[]>('/api/libraries')

export const fetchBooks = (
  libraryId: string,
  refresh = false,
  signal?: AbortSignal,
) =>
  request<BookMetadata[]>(
    `/api/libraries/${libraryId}/books?refresh=${refresh}`,
    { signal },
  )

export const fetchHistory = (libraryId: string) =>
  request<string[]>(`/api/libraries/${libraryId}/history`)

export const previewRename = (
  template: string,
  items: {
    book_id: string
    library_id: string
    overrides?: Record<string, string>
  }[],
  signal?: AbortSignal,
) =>
  request<PreviewItem[]>('/api/preview', {
    method: 'POST',
    body: JSON.stringify({ template, items }),
    signal,
  })

export const confirmRename = (template: string, items: RenameItem[]) =>
  request<RenameResponse>('/api/rename', {
    method: 'POST',
    body: JSON.stringify({ template, items, dry_run: false }),
  })

export const cleanupEmptyDirs = (libraryId: string, paths?: string[]) =>
  request<{ removed: string[]; candidates: string[]; errors: string[] }>(
    '/api/cleanup',
    {
      method: 'POST',
      body: JSON.stringify({
        library_id: libraryId,
        dry_run: paths === undefined,
        paths: paths ?? [],
      }),
    },
  )

export const scanLibrary = (libraryId: string) =>
  request<{ triggered: boolean }>(`/api/libraries/${libraryId}/scan`, {
    method: 'POST',
  })

export const clearHistory = (libraryId: string) =>
  request<{ cleared: number }>(`/api/libraries/${libraryId}/history`, {
    method: 'DELETE',
  })

export const batchUpdateSeries = (
  items: {
    book_id: string
    series_id: string | null
    series_name: string
    sequence: string
  }[],
) =>
  request<{ book_id: string; success: boolean; error: string | null }[]>(
    '/api/batch/series',
    {
      method: 'POST',
      body: JSON.stringify({ items }),
    },
  )

export interface Operation {
  id: number
  book_id: string
  old_path: string
  new_path: string
  status: 'pending' | 'succeeded' | 'failed'
  error: string | null
  created_at: string
}
export const fetchOperations = (libraryId: string) =>
  request<Operation[]>(`/api/libraries/${libraryId}/operations`)
