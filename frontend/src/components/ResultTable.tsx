import { memo, useState } from 'react';
import type { SQLExecutionResult } from '../api/types';
import { formatCell } from '../lib/format';
import { IconAlert } from './icons';

interface ResultTableProps {
  query: SQLExecutionResult;
  index: number;
}

const ROWS_PER_PAGE = 100;

export const ResultTable = memo(function ResultTable({ query, index }: ResultTableProps) {
  const data = query.data;
  const [visibleRowCount, setVisibleRowCount] = useState(ROWS_PER_PAGE);
  if (!data) return null;

  const columns = data.columns ?? [];
  const rows = data.rows ?? [];
  const empty = rows.length === 0;

  // A column counts as numeric when every populated cell is a number, so the
  // header and its values can share the same alignment.
  const numericColumns = columns.map((column) => {
    let hasValue = false;
    for (const row of rows) {
      const value = row?.[column];
      if (value === null || value === undefined) continue;
      hasValue = true;
      if (typeof value !== 'number') return false;
    }
    return hasValue;
  });
  const visibleRows = rows.slice(0, visibleRowCount);

  return (
    <div className="result">
      <div className="result__head">
        <span className="result__title">
          Query {index + 1}
          <span className="result__title-sub">result set</span>
        </span>
        <span className="result__tags">
          <span className="tag">
            {data.row_count} {data.row_count === 1 ? 'row' : 'rows'}
          </span>
          {data.truncated && (
            <span className="tag tag--warn">
              <IconAlert size={11} />
              truncated
            </span>
          )}
        </span>
      </div>

      {empty ? (
        <p className="result__empty">The statement ran successfully and matched no rows.</p>
      ) : (
        <div className="result__scroll" tabIndex={0} role="region" aria-label={`Query ${index + 1} result rows`}>
          <table className="grid">
            <thead>
              <tr>
                {columns.map((column, columnIndex) => (
                  <th
                    key={column}
                    scope="col"
                    className={numericColumns[columnIndex] ? 'is-numeric' : undefined}
                  >
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, rowIndex) => (
                <tr key={`${index}-${rowIndex}`}>
                  {columns.map((column, columnIndex) => {
                    const value = row?.[column];
                    return (
                      <td
                        key={column}
                        className={numericColumns[columnIndex] ? 'is-numeric' : undefined}
                      >
                        {formatCell(value)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {visibleRowCount < rows.length && (
        <button
          type="button"
          className="btn btn--sm result__more"
          onClick={() =>
            setVisibleRowCount((current) => Math.min(current + ROWS_PER_PAGE, rows.length))
          }
        >
          Show next {Math.min(ROWS_PER_PAGE, rows.length - visibleRowCount)} rows
        </button>
      )}

      {data.truncated && (
        <p className="result__note">
          The server capped this result at its row limit, so {data.row_count} of{' '}
          {data.total_rows.toLocaleString('en-US')} matching rows are shown.
        </p>
      )}
    </div>
  );
});
