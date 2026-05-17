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

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new ApiError(res.status, text)
  }
  return res.json()
}

export const fetchLibraries = () => request<Library[]>('/api/libraries')

export const fetchBooks = (libraryId: string) =>
  request<BookMetadata[]>(`/api/libraries/${libraryId}/books`)

export const fetchConfig = () =>
  request<{ default_template: string }>('/api/config')

export const previewRename = (template: string, items: { book_id: string; library_id: string }[]) =>
  request<PreviewItem[]>('/api/preview', {
    method: 'POST',
    body: JSON.stringify({ template, items }),
  })

export const confirmRename = (template: string, items: RenameItem[]) =>
  request<RenameResponse>('/api/rename', {
    method: 'POST',
    body: JSON.stringify({ template, items, dry_run: false }),
  })
