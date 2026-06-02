# shelf-renamer

Web app for clean file-level renaming of audiobooks in [Audiobookshelf](https://www.audiobookshelf.org/). Fetches metadata via ABS API, lets you define a naming template, previews proposed renames, then renames the folders on disk and triggers an ABS re-scan.

## Features

- Connects to any Audiobookshelf instance via API token
- Configurable naming template with live preview (e.g. `{author_lf}/{series}/{series_index_tag} - {title}`)
- Folder breadcrumb diff view before any changes — conflict detection included
- Rename history tracked in SQLite — books renamed before get a ✓ indicator; history clearable per library
- Toggle button switches between "needs renaming" (default) and "already done" views
- Title search input to filter the book list by title
- Books already in the correct location are automatically marked as done and persisted to history
- Single-file items (`.m4b`, `.mp3`, etc.) always placed in a subfolder — never left bare in the library root
- "root" badge in the book list flags file items sitting directly in the library root
- Optional password protection via `APP_PASSWORD`
- Atomic folder renames on the mounted filesystem
- Triggers ABS library re-scan after rename
- Runs as a single Docker container (amd64 + arm64)

## Quick start

```bash
cp .env.example .env
# Edit .env — set ABS_URL, ABS_TOKEN, AUDIOBOOK_PATH at minimum
docker compose up
```

Open [http://localhost:8000](http://localhost:8000).

## Configuration

All config via environment variables or `.env` file:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ABS_URL` | yes | — | Audiobookshelf base URL, e.g. `http://192.168.1.10:13378` |
| `ABS_TOKEN` | yes | — | ABS API token (Settings → Users → your user → API Token) |
| `AUDIOBOOK_PATH` | yes | — | Host path to audiobook library, mounted at `/media` in container |
| `DEFAULT_TEMPLATE` | no | `{author} - {title} ({year})` | Default naming template shown in the UI |
| `APP_PASSWORD` | no | _(empty — auth disabled)_ | Set to enable login page with password protection |
| `DB_PATH` | no | `/data/shelf-renamer.db` | SQLite database path (inside the container) |
| `UID` / `GID` | no | `1000` / `1000` | UID/GID used to write files — must match owner of `AUDIOBOOK_PATH` |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Password protection

Set `APP_PASSWORD` in your `.env` to show a login screen before the app loads. Leave it empty (the default) to run without auth.

```env
APP_PASSWORD=mysecretpassword
```

The session token is stored in `localStorage` and reused across page reloads. Restarting the container invalidates all sessions.

### Rename history

Every successful rename is recorded in a SQLite database (persisted via the `shelf-renamer-data` Docker named volume). Books that have been renamed before are marked with a green ✓ badge in the book list.

The database file lives at `DB_PATH` (default `/data/shelf-renamer.db`). Mount a host path if you want direct access:

```yaml
volumes:
  - /path/to/data:/data
```

## Naming templates

Templates use `{variable}` placeholders filled from ABS metadata:

| Variable | Example |
|----------|---------|
| `{title}` | `The Hobbit` |
| `{author}` | `J.R.R. Tolkien` |
| `{author_lf}` | `Tolkien, J.R.R.` |
| `{authors}` | `Terry Pratchett & Neil Gaiman` |
| `{year}` | `1937` |
| `{series}` | `Lord of the Rings` |
| `{series_index}` | `1` |
| `{series_index_tag}` | `#01` (zero-padded, with `#` prefix) |
| `{narrator}` | `Andy Serkis` |

Missing variables are substituted with an empty string; empty parens/brackets are cleaned up automatically. Characters forbidden in filenames (`/ \ : * ? " < > |`) are replaced with ` - `.

**Examples:**

```
{author_lf}/{series}/{series_index_tag} - {title}
  → Tolkien, J.R.R./Lord of the Rings/#01 - The Fellowship of the Ring

{author} - {title} ({year})
  → J.R.R. Tolkien - The Hobbit (1937)

{title}
  → The Hobbit
```

## docker-compose.yml

```yaml
services:
  shelf-renamer:
    image: ghcr.io/eagleffz/shelf-renamer:latest
    ports:
      - "8000:8000"
    environment:
      ABS_URL: ${ABS_URL}
      ABS_TOKEN: ${ABS_TOKEN}
      MEDIA_ROOT: /media
      DEFAULT_TEMPLATE: ${DEFAULT_TEMPLATE:-{author} - {title} ({year})}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      APP_PASSWORD: ${APP_PASSWORD:-}
      DB_PATH: /data/shelf-renamer.db
    volumes:
      - ${AUDIOBOOK_PATH}:/media:rw
      - shelf-renamer-data:/data
    user: "${UID:-1000}:${GID:-1000}"
    restart: unless-stopped

volumes:
  shelf-renamer-data:
```

## Building locally

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
DB_PATH=./shelf-renamer.db uvicorn app.main:app --reload  # dev server on :8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev   # Vite dev server on :5173, proxies /api → :8000
```

**Docker:**
```bash
docker build -t shelf-renamer:local .
docker run -p 8000:8000 \
  -e ABS_URL=http://your-abs:13378 \
  -e ABS_TOKEN=your-token \
  -e APP_PASSWORD=secret \
  -v /path/to/audiobooks:/media \
  -v /path/to/data:/data \
  shelf-renamer:local
```

## CI / Docker images

GitHub Actions builds and pushes to `ghcr.io/eagleffz/shelf-renamer` on every push to `main`:

| Tag | Description |
|-----|-------------|
| `latest` | Most recent main build |
| `<sha>` | Short git SHA |
| `YYYY-MM-DD` | Build date |

Platforms: `linux/amd64`, `linux/arm64` (NAS / Raspberry Pi).

## API

All endpoints prefixed with `/api`. Endpoints marked 🔒 require `Authorization: Bearer <token>` when `APP_PASSWORD` is set.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/health` | — | ABS connectivity check |
| `GET` | `/api/config` | — | Server-side defaults + `auth_required` flag |
| `POST` | `/api/auth/login` | — | Exchange password for session token |
| `GET` | `/api/libraries` | 🔒 | List ABS libraries |
| `GET` | `/api/libraries/{id}/books` | 🔒 | Books in a library |
| `GET` | `/api/libraries/{id}/history` | 🔒 | Book IDs previously renamed in this library |
| `DELETE` | `/api/libraries/{id}/history` | 🔒 | Clear rename history for a library |
| `POST` | `/api/libraries/{id}/verify` | 🔒 | Mark books already in correct location as done |
| `POST` | `/api/preview` | 🔒 | Preview renames (no filesystem write) |
| `POST` | `/api/rename` | 🔒 | Execute renames + trigger ABS scan |

## Notes

- Renames are at the **folder** level by default. Single-file items (e.g. `.m4b`) are renamed at the file level.
- `os.rename()` is used — atomic on POSIX within the same filesystem. No rollback on partial batch failure; per-book success/error is reported.
- The container user (UID 1000 by default) must have write permission on the mounted volume. Set `UID`/`GID` in `.env` to match your file ownership.
- After rename, ABS re-scans the affected library automatically. If the scan request fails (e.g. token expired), renames are still reported as successful.
- Restarting the container generates a new session token — any stored browser token becomes invalid and a re-login is required.
