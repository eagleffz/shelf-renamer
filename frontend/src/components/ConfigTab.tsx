import { useEffect, useState } from 'react'
import type { AppConfig } from '../api'

interface Props {
  config: AppConfig
}

export function ConfigTab({ config }: Props) {
  const [absOk, setAbsOk] = useState<boolean | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setAbsOk(d.abs_reachable))
      .catch(() => setAbsOk(false))
  }, [])

  const defaultEntry = { abs_root: '(fallback)', container_root: config.media_root }
  const entries = config.volume_map.length > 0 ? config.volume_map : [defaultEntry]

  return (
    <div className="config-tab">
      <h2 className="config-section-title">Instance</h2>
      <table className="config-table">
        <tbody>
          <tr>
            <td>Version</td>
            <td><code>{config.version}</code></td>
          </tr>
          <tr>
            <td>ABS URL</td>
            <td>
              <code>{config.abs_url}</code>
              {absOk === null && <span className="cfg-badge cfg-checking">checking…</span>}
              {absOk === true && <span className="cfg-badge cfg-ok">✓ reachable</span>}
              {absOk === false && <span className="cfg-badge cfg-error">✗ unreachable</span>}
            </td>
          </tr>
          <tr>
            <td>Auth</td>
            <td>{config.auth_required ? 'Password protected' : 'Open (no password)'}</td>
          </tr>
          <tr>
            <td>Default template</td>
            <td><code>{config.default_template}</code></td>
          </tr>
        </tbody>
      </table>

      <h2 className="config-section-title">Volume map</h2>
      <p className="config-hint">
        Each row maps an ABS-reported library root to the container mount point shelf-renamer uses for filesystem access.
      </p>
      <table className="config-table">
        <thead>
          <tr>
            <th>ABS root (reported by ABS)</th>
            <th>Container mount point</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={i}>
              <td><code>{e.abs_root}</code></td>
              <td><code>{e.container_root}</code></td>
            </tr>
          ))}
          {config.volume_map.length > 0 && (
            <tr className="cfg-fallback-row">
              <td><code>(everything else)</code></td>
              <td><code>{config.media_root}</code> <span className="cfg-badge">fallback</span></td>
            </tr>
          )}
        </tbody>
      </table>

      <h2 className="config-section-title">How to add a second library</h2>
      <pre className="config-pre">{`# .env
AUDIOBOOK_PATH=/srv/audiobooks    # primary — mounts to /media
AUDIOBOOK_PATH_2=/srv/podcasts    # secondary — mounts to /media2
VOLUME_MAP=/audiobooks=/media,/podcasts=/media2

# docker-compose.yml — uncomment the second volume line
volumes:
  - \${AUDIOBOOK_PATH}:/media:rw
  - \${AUDIOBOOK_PATH_2}:/media2:rw`}</pre>
    </div>
  )
}
