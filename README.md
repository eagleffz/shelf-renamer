# shelf-renamer

Web app for clean file-level renaming of audiobooks in [Audiobookshelf](https://www.audiobookshelf.org/). Fetches metadata via ABS API, lets you define a naming template, previews proposed renames, then renames the folders on disk and triggers an ABS re-scan.

![Browse → Preview → Rename flow](https://via.placeholder.com/800x400?text=Browse+%E2%86%92+Preview+%E2%86%92+Rename)

## Features

- Connects to any Audiobookshelf instance via API token
- Configurable naming template with live preview (e.g. `{author} - {title} ({year})`)
- Diff view before any changes are made — conflict detection included
- Atomic folder renames on the mounted filesystem
- Triggers ABS library re-scan after rename
- Runs as a single Docker container (amd64 + arm64)

## Quick start

```bash
cp .env.example .env
# Edit .env with your ABS URL, token, and audiobook path
docker compose up
```

Open [http://localhost:8000](http://localhost:8000).

## Configuration

All config via environment variables (or `.env` file):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ABS_URL` | yes | — | Audiobookshelf base URL, e.g. `http://192.168.1.10:13378` |
| `ABS_TOKEN` | yes | — | ABS API token (Settings → Users → your user → API Token) |
| `AUDIOBOOK_PATH` | yes | — | Host path to audiobook library, mounted at `/media` in container |
| `DEFAULT_TEMPLATE` | no | `{author} - {title} ({year})` | Default naming template |
| `UID` / `GID` | no | `1000` / `1000` | UID/GID used to write files — must match owner of `AUDIOBOOK_PATH` |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

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
| `{narrator}` | `Andy Serkis` |

Missing variables are substituted with an empty string; empty parens/brackets are cleaned up automatically. Characters forbidden in filenames (`/ \ : * ? " < > |`) are replaced with `-`.

**Examples:**

```
{author} - {title} ({year})          →  J.R.R. Tolkien - The Hobbit (1937)
{author_lf} - {series} {series_index} - {title}  →  Tolkien, J.R.R. - Lord of the Rings 1 - The Fellowship of the Ring
{title}                               →  The Hobbit
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
    volumes:
      - ${AUDIOBOOK_PATH}:/media:rw
    user: "${UID:-1000}:${GID:-1000}"
    restart: unless-stopped
```

## Building locally

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
uvicorn app.main:app --reload  # dev server on :8000
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
  -v /path/to/audiobooks:/media \
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

All endpoints are prefixed with `/api`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | ABS connectivity check |
| `GET` | `/api/config` | Server-side defaults |
| `GET` | `/api/libraries` | List ABS libraries |
| `GET` | `/api/libraries/{id}/books` | Books in a library |
| `POST` | `/api/preview` | Preview renames (no filesystem write) |
| `POST` | `/api/rename` | Execute renames + trigger ABS scan |

## Notes

- Renames are at the **folder** level, not individual files inside.
- `os.rename()` is used — atomic on POSIX (same filesystem). No rollback on partial batch failure; per-book success/error is reported.
- The container user (UID 1000 by default) must have write permission on the mounted volume. Set `UID`/`GID` in `.env` to match your file ownership.
- After rename, ABS re-scans the affected library automatically. If the scan request fails (e.g. token expired), renames are still reported as successful.
