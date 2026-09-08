import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import type { AppConfig, BookMetadata, PreviewItem } from './api'
import * as api from './api'

vi.mock('./api', async (importOriginal) => {
  const original = await importOriginal<typeof api>()
  return {
    ...original,
    fetchConfig: vi.fn(),
    fetchSession: vi.fn(),
    fetchLibraries: vi.fn(),
    fetchBooks: vi.fn(),
    fetchHistory: vi.fn(),
    previewRename: vi.fn(),
    batchUpdateSeries: vi.fn(),
    confirmRename: vi.fn(),
  }
})

const config: AppConfig = {
  default_template: '{title}',
  auth_required: false,
  version: 'test',
  abs_url: 'http://abs.test',
  media_root: '/media',
  volume_map: [],
}
const books: BookMetadata[] = ['First Book', 'Second Book'].map((title, i) => ({
  id: `b${i}`,
  library_id: 'lib',
  title,
  authors: [{ id: 'a', name: 'Author Name' }],
  series: 'Series',
  series_id: 'series',
  series_index: i + 1,
  published_year: '2020',
  narrator: null,
  abs_path: `/abs/${title}`,
  abs_library_root: '/abs',
  is_file: false,
  file_extension: '',
}))
function preview(
  template: string,
  items: {
    book_id: string
    library_id: string
    overrides?: Record<string, string>
  }[],
): PreviewItem[] {
  return items.map((item) => ({
    book_id: item.book_id,
    library_id: item.library_id,
    current_path: `/media/${item.book_id}`,
    proposed_path: `/media/new/${item.book_id}`,
    current_name: item.book_id,
    proposed_name: item.overrides?.title ?? `${template}/${item.book_id}`,
    conflict: false,
    no_change: template === '{title}',
    error: null,
    warnings: [],
    preview_token: 'signed-plan',
  }))
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  localStorage.setItem('shelf-library', 'lib')
  vi.mocked(api.fetchConfig).mockResolvedValue(config)
  vi.mocked(api.fetchLibraries).mockResolvedValue([
    { id: 'lib', name: 'Audiobooks', folders: ['/abs'] },
    { id: 'other', name: 'Other library', folders: ['/other'] },
  ])
  vi.mocked(api.fetchBooks).mockResolvedValue(books)
  vi.mocked(api.fetchHistory).mockResolvedValue(['b0'])
  vi.mocked(api.previewRename).mockImplementation(async (template, items) =>
    preview(template, items),
  )
})

describe('library workflow', () => {
  it('shows a retry action when startup fails', async () => {
    vi.mocked(api.fetchConfig).mockRejectedValueOnce(
      new Error('Server offline'),
    )
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Server offline')
    await userEvent.click(
      screen.getByRole('button', { name: 'Retry connection' }),
    )
    expect(
      await screen.findByRole('heading', { name: 'Rename your audiobooks' }),
    ).toBeInTheDocument()
  })

  it('reclassifies previously renamed books when the template changes', async () => {
    render(<App />)
    await screen.findByRole('button', { name: 'Matches (2)' })
    fireEvent.change(screen.getByLabelText('Naming template'), {
      target: { value: '{author}/{title}' },
    })
    await screen.findByRole('button', { name: 'Needs changes (2)' })
    expect(
      screen.getByRole('checkbox', { name: 'Select First Book' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('History', { selector: 'span' }),
    ).toBeInTheDocument()
  })

  it('keeps hidden selections visible in the count and selects only visible rows', async () => {
    render(<App />)
    await screen.findByRole('button', { name: 'Matches (2)' })
    await userEvent.click(screen.getByRole('button', { name: 'All (2)' }))
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'Select First Book' }),
    )
    await userEvent.type(screen.getByRole('searchbox'), 'Second')
    expect(
      screen.getByText('1 selected · 1 hidden by filters'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', { name: 'Select all visible books' }),
    ).not.toBeChecked()
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'Select all visible books' }),
    )
    expect(
      screen.getByText('2 selected · 1 hidden by filters'),
    ).toBeInTheDocument()
    await userEvent.click(
      screen.getByRole('button', { name: 'Clear selection' }),
    )
    expect(screen.getByText('0 selected')).toBeInTheDocument()
  })

  it('preserves batch edits across tabs and shows per-row save errors', async () => {
    vi.mocked(api.batchUpdateSeries).mockResolvedValue([
      { book_id: 'b0', success: false, error: 'ABS unavailable' },
    ])
    render(<App />)
    await screen.findByRole('heading', { name: 'Rename your audiobooks' })
    await userEvent.click(screen.getByRole('button', { name: 'Batch Editor' }))
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Series to edit' }),
      'Series',
    )
    fireEvent.change(screen.getByLabelText('Sequence for First Book'), {
      target: { value: '5' },
    })
    await userEvent.click(screen.getByRole('button', { name: 'Library' }))
    await userEvent.click(screen.getByRole('button', { name: 'Batch Editor' }))
    expect(screen.getByLabelText('Sequence for First Book')).toHaveValue('5')
    await userEvent.click(screen.getByRole('button', { name: 'Save 1 change' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'ABS unavailable',
    )
    expect(screen.getByRole('button', { name: 'Save 1 change' })).toBeEnabled()
  })

  it('ignores stale library responses after switching libraries', async () => {
    let resolveOld!: (value: BookMetadata[]) => void
    vi.mocked(api.fetchBooks).mockImplementation((id) =>
      id === 'lib'
        ? new Promise((resolve) => {
            resolveOld = resolve
          })
        : Promise.resolve([
            {
              ...books[1],
              id: 'other-book',
              library_id: 'other',
              title: 'Other book',
            },
          ]),
    )
    render(<App />)
    await screen.findByRole('heading', { name: 'Rename your audiobooks' })
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Audiobook library' }),
      'other',
    )
    await userEvent.click(screen.getByRole('button', { name: 'All (1)' }))
    expect(
      await screen.findByRole('checkbox', { name: 'Select Other book' }),
    ).toBeInTheDocument()
    resolveOld(books)
    await waitFor(() =>
      expect(
        screen.queryByRole('checkbox', { name: 'Select First Book' }),
      ).not.toBeInTheDocument(),
    )
  })

  it('disables rename until an override has a fresh preview', async () => {
    vi.mocked(api.fetchConfig).mockResolvedValue({
      ...config,
      default_template: '{author}/{title}',
    })
    render(<App />)
    await screen.findByRole('button', { name: 'Needs changes (2)' })
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'Select First Book' }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Preview 1 books' }),
    )
    await userEvent.click(
      await screen.findByRole('button', {
        name: 'Edit filename metadata for First Book',
      }),
    )
    let resolvePreview!: (value: PreviewItem[]) => void
    vi.mocked(api.previewRename).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePreview = resolve
        }),
    )
    const title = within(
      screen.getByRole('region', { name: 'Rename library' }),
    ).getByLabelText('Title', { exact: true })
    fireEvent.change(title, { target: { value: 'Edited title' } })
    fireEvent.blur(title)
    expect(
      screen.getByRole('button', { name: 'Rename 1 books' }),
    ).toBeDisabled()
    resolvePreview(
      preview('{author}/{title}', [
        {
          book_id: 'b0',
          library_id: 'lib',
          overrides: { title: 'Edited title' },
        },
      ]),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Rename 1 books' }),
      ).toBeEnabled(),
    )
    expect(
      screen.getByText('Edited title', { selector: '.path-file-label' }),
    ).toBeInTheDocument()
  })
})
