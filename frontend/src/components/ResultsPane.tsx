import type { RenameResponse } from '../api'

interface Props {
  response: RenameResponse
  onReset: () => void
  onRetry: () => void
  onScan: () => void
  working: boolean
}

export function ResultsPane({
  response,
  onReset,
  onRetry,
  onScan,
  working,
}: Props) {
  const succeeded = response.results.filter((r) => r.success)
  const failed = response.results.filter((r) => !r.success)

  return (
    <div className="results-pane">
      <h2>Rename Results</h2>
      <p className="summary" role="status">
        {succeeded.length} renamed, {failed.length} failed.
        {response.scan_triggered ? ' ABS re-scan triggered.' : ''}
      </p>
      {response.scan_errors.length > 0 && (
        <div role="alert" className="error-banner">
          Files were moved, but the ABS rescan request failed.{' '}
          <button
            className="btn btn-secondary"
            disabled={working}
            onClick={onScan}
          >
            Retry rescan
          </button>
        </div>
      )}
      {succeeded
        .filter((r) => r.error)
        .map((r) => (
          <p role="alert" key={r.book_id}>
            {r.error}
          </p>
        ))}

      {failed.length > 0 && (
        <>
          <h3>Failed</h3>
          <table className="results-table">
            <thead>
              <tr>
                <th>Book</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {failed.map((r) => (
                <tr key={r.book_id} className="row-fail">
                  <td className="monospace">{r.old_path}</td>
                  <td>{r.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {succeeded.length > 0 && (
        <>
          <h3>Succeeded</h3>
          <table className="results-table">
            <thead>
              <tr>
                <th>Old name</th>
                <th></th>
                <th>New name</th>
              </tr>
            </thead>
            <tbody>
              {succeeded.map((r) => (
                <tr key={r.book_id} className="row-ok">
                  <td className="monospace old-name">{r.old_path}</td>
                  <td className="arrow">→</td>
                  <td className="monospace new-name">{r.new_path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {failed.length > 0 && (
        <button
          className="btn btn-primary"
          disabled={working}
          onClick={onRetry}
        >
          Preview failed books again
        </button>
      )}
      <button
        className="btn btn-secondary"
        disabled={working}
        onClick={onReset}
      >
        Back to library
      </button>
    </div>
  )
}
