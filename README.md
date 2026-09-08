# shelf-renamer

Rename audiobook folders and single-file items managed by [Audiobookshelf](https://www.audiobookshelf.org/). Choose a naming template, review proposed paths, apply changes, and request an ABS rescan.

## Features

- Validated naming templates, example output, metadata warnings, and presets saved per library in your browser.
- Folder breadcrumb preview with duplicate and overlapping path detection across the batch.
- Signed previews expire after 30 minutes; changed metadata, overrides, or source paths require a new preview.
- All / Needs changes / Matches filters reflect the current template. A separate History badge indicates earlier renames.
- Search by title, author, or series; selection counts include books hidden by filters.
- Batch Editor: select a series, sort and auto-number or edit positions, preserve edits across tabs, and retry failed rows. Updates preserve other series memberships.
- Persistent operation history with full paths, per-book results, and interrupted-operation records.
- Library maintenance includes a review of empty folders before deletion and explicit rescan recovery.
- Atomic renames that cannot overwrite an existing destination. Symlinks inside libraries are rejected.
- Optional password protection with expiring, revocable sessions.
- Single Docker container for Linux amd64 and arm64.

## Quick start

```bash
cp .env.example .env
# Set ABS_URL, ABS_TOKEN, and AUDIOBOOK_PATH in .env
docker compose up -d
```

Open [localhost:8000](http://localhost:8000). Choose a library, select books, and click Preview. Review the destination paths before clicking Rename. Blocked books are excluded. Filename overrides only affect the rename; the Batch Editor edits ABS series metadata.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `ABS_URL` | `http://localhost:13378` | Audiobookshelf base URL; configure for your instance |
| `ABS_TOKEN` | empty | ABS API token with access to the library and metadata updates |
| `AUDIOBOOK_PATH` | required by Compose | Host path mounted at `/media` |
| `MEDIA_ROOT` | `/media` | Container path for single-volume fallback |
| `VOLUME_MAP` | empty | Explicit `ABS_ROOT=CONTAINER_ROOT` mappings, comma-separated |
| `DEFAULT_TEMPLATE` | `{author_lf}/{series}/{series_index_tag} - {title}` in backend; `{author} - {title} ({year})` in Compose | Initial template unless a browser preset was saved |
| `APP_PASSWORD` | empty | Enable login; empty disables authentication |
| `ALLOWED_ORIGINS` | empty | Comma-separated trusted browser origins for writes and CORS, in addition to same-origin writes |
| `DB_PATH` | `/data/shelf-renamer.db` | Persistent SQLite database |
| `UID` / `GID` | `1000` / `1000` in Compose | Must have permission to write the mounted library |
| `LOG_LEVEL` | `INFO` | Server logging level |
| `DEBUG` | `false` | Permit the local Vite development origin |

### Multiple libraries and folders

Mount each host path and configure its ABS-to-container mapping:

```yaml
environment:
  VOLUME_MAP: /audiobooks=/media,/podcasts=/media2
volumes:
  - /srv/audiobooks:/media:rw
  - /srv/podcasts:/media2:rw
```

The ABS root is the folder path shown in ABS → Libraries → Edit → Folders. Longer mappings take priority. Each item's actual library folder is used, including libraries with multiple folders.

With `VOLUME_MAP` empty, the app uses the single-volume fallback at `MEDIA_ROOT`. Configure explicit mappings for multiple roots. With mappings present, every library must match an entry; unmapped libraries are blocked rather than silently falling back to another mount. Entries must use absolute paths. Renames cannot escape their library root or follow symlinks inside a library.

### Authentication

Set `APP_PASSWORD` in `.env` to enable login. Sessions use HttpOnly, SameSite=Strict cookies and expire after 12 hours. HTTPS connections also receive Secure cookies. Sign out revokes the session on the server. Restarting the container invalidates all sessions and previews. Login attempts are rate limited.

Use HTTPS for access over untrusted networks. A reverse proxy must preserve the public Host and scheme; configure trusted forwarded headers for Uvicorn as appropriate for that proxy.

If a reverse proxy causes `Cross-origin writes are not allowed`, explicitly whitelist the URL you use to open shelf-renamer in `.env`:

```env
ALLOWED_ORIGINS=https://renamer.example.com,http://nas.local:8000
```

The Compose file passes this setting to the container. With an existing custom Compose file, add `ALLOWED_ORIGINS: ${ALLOWED_ORIGINS:-}` under the service's `environment`. Recreate the container with `docker compose up -d` after changing it.

Use origins only: scheme, hostname, and optional port. Multiple entries are comma-separated; surrounding whitespace and a trailing slash are accepted. Paths, credentials, query strings, fragments, and wildcards are rejected at startup. Scheme and non-default port must match exactly; subdomains are not automatically included. An empty value keeps the default same-origin protection. `DEBUG=true` additionally permits `http://localhost:5173`.

The same allowlist is used for the write guard and credentialed CORS preflight/response headers. It does not bypass login or change SameSite cookie behavior. You should still configure forwarded headers correctly for HTTPS cookie handling.

The supported deployment uses one Uvicorn worker, as configured in the Docker image. Session and preview-signing state is process-local: do not add workers or load-balanced replicas without shared session/signing storage. A filesystem lock beside the database also coordinates mutations across processes sharing that database.

### History and recovery

Each rename is journaled before disk changes and completed individually in SQLite. Repeated renames retain all operation records. The named `shelf-renamer-data` volume persists the database. To use a host directory, mount it at `/data` with write permission for the container user.

The History tab displays the latest 500 operations. A `pending` entry may have moved files before an interruption: inspect both paths before recovery. The app never blindly retries an interrupted move. Clearing history badges does not delete the operation log. Checking whether books match a template is read-only.

Existing successful history is imported on first startup of v1.20.0. Records already discarded by previous versions cannot be reconstructed. Back up the data volume before upgrading.

## Naming templates

| Variable | Example |
|----------|---------|
| `{title}` | `The Hobbit` |
| `{author}` | `J.R.R. Tolkien` |
| `{author_lf}` | `Tolkien, J.R.R.` |
| `{authors}` | `Terry Pratchett & Neil Gaiman` |
| `{year}` | `1937` |
| `{series}` | `The Lord of the Rings` |
| `{series_index}` | `1` |
| `{series_index_tag}` | `#1` (decimals supported) |
| `{narrator}` | `Andy Serkis` |

Use `/` to create folder levels. Known variables with missing metadata become empty strings; empty segments, parentheses, and brackets are cleaned up. Unknown variables, malformed braces, formatting expressions, and traversal segments are rejected. Forbidden filename characters and control characters become spaces.

```text
{author_lf}/{series}/{series_index_tag} - {title}
→ Tolkien, J.R.R./The Lord of the Rings/#1 - The Fellowship of the Ring

{author} - {title} ({year})
→ J.R.R. Tolkien - The Hobbit (1937)
```

Single-file items always retain their extension, even when the final template segment is empty, and always reside in a subfolder. A `root` badge identifies files currently sitting directly in the library root.

## Local development

Backend requires Python 3.12; frontend builds use Node 24.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
DB_PATH=./shelf-renamer.db uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
npm run dev
```

Vite runs on port 5173 and proxies `/api` to port 8000. To build the production image:

```bash
docker build --build-arg VERSION=dev -t shelf-renamer:local .
```

Runtime dependencies are pinned in `backend/requirements.txt`; test dependencies are separate in `requirements-dev.txt`. Update the locks with Python 3.12 and pip-tools from the repository root:

```bash
pip-compile --upgrade --strip-extras --output-file backend/requirements.txt backend/requirements.in
pip-compile --strip-extras --output-file backend/requirements-dev.txt backend/requirements-dev.in
```

CI runs backend tests, frontend interaction tests, lint, and the production frontend build. Main builds publish amd64/arm64 images to `ghcr.io/eagleffz/shelf-renamer` with `latest`, short commit SHA, and date tags. When the checked-out commit has an exact release tag, that tag is published too. Push the main commit and its release tag together to publish the correct release version.

## API

Protected routes require the login session cookie when `APP_PASSWORD` is set. API documentation is also available at `/docs`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/live` | Local process liveness; Docker healthcheck |
| GET | `/api/health` | ABS connectivity check |
| GET | `/api/config` | Defaults and connection configuration |
| POST | `/api/auth/login` | Start a cookie session |
| GET | `/api/auth/session` | Check session |
| POST | `/api/auth/logout` | Revoke session |
| GET | `/api/libraries` | List libraries |
| GET | `/api/libraries/{id}/books` | List books; `?refresh=true` bypasses cache |
| GET / DELETE | `/api/libraries/{id}/history` | Read or clear previously-renamed badges |
| GET | `/api/libraries/{id}/operations` | Latest 500 operation records |
| POST | `/api/libraries/{id}/scan` | Request an ABS rescan |
| POST | `/api/batch/series` | Update series positions with per-item results |
| POST | `/api/preview` | Build signed rename previews without writes |
| POST | `/api/rename` | Validate the preview, rename, and request scans |
| POST | `/api/cleanup` | Preview or remove reviewed empty folders |

Rename requests must include each item's `current_path` and `preview_token` from `/api/preview`, with the same template and overrides. Unsafe or stale plans return HTTP 409 before any move. The old client-supplied `/verify` endpoint was removed.

Cleanup accepts `{ "library_id": "...", "dry_run": true }` and returns candidate paths. After review, send those exact paths in `paths` with `dry_run: false`. Library roots and nonempty folders are never removed.

## Filesystem guarantees and limits

Linux uses `renameat2(RENAME_NOREPLACE)` and macOS uses `renameatx_np(RENAME_EXCL)` with directory descriptors that reject symlinks. Unsupported platforms/filesystems fail safely. Moves must remain on the same filesystem.

A batch is not a transaction: completed moves remain completed if another item fails. Each result is recorded separately. ABS scan failures are reported separately and can be retried. Refresh the library after ABS finishes scanning to see updated paths.
