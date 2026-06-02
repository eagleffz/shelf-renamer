# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

shelf-renamer is a web app for renaming audiobook folders/files managed by [Audiobookshelf](https://www.audiobookshelf.org/). It fetches metadata via the ABS API, lets users define a naming template, previews proposed renames, executes them on disk, and triggers an ABS re-scan.

## Development commands

**Backend** (Python / FastAPI):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Dev server (port 8000), hot-reload
DB_PATH=./shelf-renamer.db uvicorn app.main:app --reload

# Tests
pytest -v
# Single test file
pytest tests/test_renamer.py -v
```

**Frontend** (React / Vite / TypeScript):
```bash
cd frontend
npm install
npm run dev      # Vite dev server on :5173, proxies /api → :8000
npm run build    # tsc -b && vite build
npm run lint     # eslint
```

**Docker** (production):
```bash
docker build -t shelf-renamer:local .
docker compose up
```

## Architecture

Single Docker container: FastAPI backend serves built frontend static files from `backend/frontend/dist/`. In dev, Vite runs separately on `:5173` and proxies `/api` to `:8000`.

### Backend (`backend/app/`)

| File | Role |
|------|------|
| `main.py` | FastAPI app, all route handlers |
| `abs_client.py` | Async httpx wrapper around ABS API — fetches libraries/books, triggers scans |
| `renamer.py` | Template rendering (`render_path_template`) and `safe_rename` (atomic `os.rename`) |
| `models.py` | Pydantic models shared between API and internal logic |
| `config.py` | `Settings` via pydantic-settings, loaded from env / `.env`. Cached via `@lru_cache` |
| `auth.py` | Optional password auth — generates a session token on startup, verifies Bearer tokens |
| `database.py` | aiosqlite — single `rename_history` table tracking successful renames |

**Path translation**: ABS reports absolute paths on the ABS host. The backend maps these to container paths via `_container_path()` in `main.py`, which replaces the ABS library root with `settings.media_root` (defaults to `/media`).

**Template rendering** (`renamer.py`): Templates like `{author_lf}/{series}/{series_index_tag} - {title}` are split on `/` into segments. Each segment is formatted, sanitized (forbidden filename chars → space), and cleaned (empty parens/brackets, trailing separators). Empty segments are dropped. For file items (`is_file=True`), the original extension is appended to the last segment.

**File vs folder items**: `abs_client.py` checks the path extension against `AUDIO_EXTENSIONS`. Single-file audiobooks (`.m4b`, etc.) get `is_file=True` and are renamed at the file level; multi-file books are renamed at the folder level.

### Frontend (`frontend/src/`)

Single-page app with three phases managed in `App.tsx`:
- `browse` — library selector + book table with checkbox selection
- `preview` — diff view (`PreviewTable`) with per-book field overrides
- `results` — success/error summary (`ResultsPane`)

All API calls live in `api.ts`. Auth token stored in `localStorage` under `shelf-renamer-token`. A 401 response clears the token and triggers re-authentication via `setUnauthorizedHandler`.

Background debounced preview (700ms) runs on every template/book change in `App.tsx` to populate `alreadyCorrectIds` — used to power the "Show changes" filter without a separate user action.

### Key data flow

1. User selects library → `GET /api/libraries/{id}/books` fetches all books (paginated from ABS)
2. User selects books + sets template → `POST /api/preview` → backend resolves paths, returns `PreviewItem[]` with `current_name`, `proposed_name`, `conflict`, `no_change`
3. User confirms → `POST /api/rename` → backend calls `safe_rename` per book, records to SQLite, triggers ABS scan
4. `GET /api/libraries/{id}/history` returns book IDs previously renamed (shown as ✓ badge)

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `ABS_URL` | `http://localhost:13378` | ABS instance base URL |
| `ABS_TOKEN` | `""` | ABS API token |
| `MEDIA_ROOT` / `AUDIOBOOK_PATH` | `/media` | Host audiobook path, mounted at `/media` |
| `DEFAULT_TEMPLATE` | `{author_lf}/{series}/{series_index_tag} - {title}` | |
| `APP_PASSWORD` | `""` | Enables login when set |
| `DB_PATH` | `/data/shelf-renamer.db` | SQLite path |
| `DEBUG` | `false` | Enables CORS for `localhost:5173` |
| `LOG_LEVEL` | `INFO` | |
