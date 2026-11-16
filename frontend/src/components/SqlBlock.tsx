import { memo, useMemo } from 'react';
import type { SQLExecutionResult } from '../api/types';
import { tokenizeSql } from '../lib/sqlTokens';
import { CopyButton } from './CopyButton';
import { IconAlert, IconCheck } from './icons';

export const SqlCode = memo(function SqlCode({ sql }: { sql: string }) {
  const tokens = useMemo(() => tokenizeSql(sql), [sql]);

  return (
    <pre className="sql" tabIndex={0} role="region" aria-label="Executed SQL">
      <code>
        {tokens.map((token, index) => (
          <span className={`tok tok--${token.kind}`} key={index}>
            {token.text}
          </span>
        ))}
      </code>
    </pre>
  );
});

interface SqlBlockProps {
  query: SQLExecutionResult;
  index: number;
}

export function SqlBlock({ query, index }: SqlBlockProps) {
  const sql = query.executed_sql ?? query.requested_sql;
  const rewritten =
    Boolean(query.executed_sql) && query.executed_sql !== query.requested_sql;

  return (
    <article className={`sqlblock${query.status === 'failed' ? ' is-failed' : ''}`}>
      <header className="sqlblock__head">
        <span className="sqlblock__index mono-label">Query {index + 1}</span>
        {query.status === 'success' ? (
          <span className="sqlblock__state sqlblock__state--ok">
            <IconCheck size={12} />
            Executed
          </span>
        ) : (
          <span className="sqlblock__state sqlblock__state--bad">
            <IconAlert size={12} />
            Failed
          </span>
        )}
        <span className="sqlblock__spacer" />
        <CopyButton value={sql} label="SQL" />
      </header>

      <SqlCode sql={sql} />

      {rewritten && (
        <p className="sqlblock__note">
          The read-only validator rewrote this statement before it reached the database.
        </p>
      )}

      {query.status === 'failed' && query.error && (
        <p className="sqlblock__error">
          <IconAlert size={13} />
          <span>{query.error}</span>
        </p>
      )}
    </article>
  );
}
