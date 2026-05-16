import type { RenameResponse } from '../api'

interface Props {
  response: RenameResponse
  onReset: () => void
}

export function ResultsPane({ response, onReset }: Props) {
  const succeeded = response.results.filter((r) => r.success)
  const failed = response.results.filter((r) => !r.success)

  return (
    <div className="results-pane">
      <h2>Rename Results</h2>
      <p className="summary">
        {succeeded.length} renamed, {failed.length} failed.
        {response.scan_triggered ? ' ABS re-scan triggered.' : ''}
      </p>

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
                  <td className="monospace">{r.old_path.split('/').at(-1)}</td>
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
                  <td className="monospace old-name">{r.old_path.split('/').at(-1)}</td>
                  <td className="arrow">→</td>
                  <td className="monospace new-name">{r.new_path.split('/').at(-1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <button className="btn btn-secondary" onClick={onReset}>
        Start over
      </button>
    </div>
  )
}
