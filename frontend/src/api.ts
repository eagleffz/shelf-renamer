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
}

export interface RenameItem {
  book_id: string
  library_id: string
  current_path: string
  overrides?: Record<string, string>
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
}

export interface AppConfig {
  default_template: string
  auth_required: boolean
  version: string
  abs_url: string
}

const TOKEN_KEY = 'shelf-renamer-token'

export const getAuthToken = () => localStorage.getItem(TOKEN_KEY) ?? ''
export const setAuthToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)
export const clearAuthToken = () => localStorage.removeItem(TOKEN_KEY)

let _onUnauthorized: (() => void) | null = null
export const setUnauthorizedHandler = (fn: () => void) => { _onUnauthorized = fn }

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(path, { headers, ...options })
  if (!res.ok) {
    if (res.status === 401 && _onUnauthorized) {
      clearAuthToken()
      _onUnauthorized()
    }
    const text = await res.text()
    throw new ApiError(res.status, text)
  }
  return res.json()
}

export const fetchConfig = () => request<AppConfig>('/api/config')

export const login = (password: string) =>
  request<{ token: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })

export const fetchLibraries = () => request<Library[]>('/api/libraries')

export const fetchBooks = (libraryId: string) =>
  request<BookMetadata[]>(`/api/libraries/${libraryId}/books`)

export const fetchHistory = (libraryId: string) =>
  request<string[]>(`/api/libraries/${libraryId}/history`)

export const previewRename = (
  template: string,
  items: { book_id: string; library_id: string; overrides?: Record<string, string> }[],
) =>
  request<PreviewItem[]>('/api/preview', {
    method: 'POST',
    body: JSON.stringify({ template, items }),
  })

export const confirmRename = (template: string, items: RenameItem[]) =>
  request<RenameResponse>('/api/rename', {
    method: 'POST',
    body: JSON.stringify({ template, items, dry_run: false }),
  })

export const cleanupEmptyDirs = () =>
  request<{ removed: string[] }>('/api/cleanup', { method: 'POST' })

export const scanLibrary = (libraryId: string) =>
  request<{ triggered: boolean }>(`/api/libraries/${libraryId}/scan`, { method: 'POST' })

export const clearHistory = (libraryId: string) =>
  request<{ cleared: number }>(`/api/libraries/${libraryId}/history`, { method: 'DELETE' })

export const verifyBooks = (
  libraryId: string,
  items: { book_id: string; library_id: string; current_path: string }[],
) =>
  request<{ marked: number }>(`/api/libraries/${libraryId}/verify`, {
    method: 'POST',
    body: JSON.stringify({ items }),
  })
