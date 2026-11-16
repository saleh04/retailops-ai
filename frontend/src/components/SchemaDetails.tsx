import { memo } from 'react';
import type { DescribeTableData, SchemaToolResult } from '../api/types';
import { IconAlert } from './icons';

function isDescribeData(data: unknown): data is DescribeTableData {
  return Boolean(data) && typeof data === 'object' && 'columns' in (data as object);
}

function SchemaEntry({ result }: { result: SchemaToolResult }) {
  if (result.status === 'failed') {
    return (
      <div className="schema__entry schema__entry--failed">
        <span className="schema__tool mono-code">{result.tool_name}</span>
        <p className="schema__error">
          <IconAlert size={13} />
          {result.error}
        </p>
      </div>
    );
  }

  if (result.tool_name === 'list_tables' && Array.isArray(result.data)) {
    return (
      <div className="schema__entry">
        <span className="schema__tool mono-code">list_tables</span>
        <div className="schema__tables">
          {result.data.length === 0 ? (
            <span className="schema__empty">No tables were returned.</span>
          ) : (
            result.data.map((table) => (
              <span className="tag" key={table}>
                {table}
              </span>
            ))
          )}
        </div>
      </div>
    );
  }

  if (isDescribeData(result.data)) {
    const described = result.data;
    return (
      <div className="schema__entry">
        <span className="schema__tool mono-code">describe_table</span>
        <p className="schema__table-name">{described.table_name}</p>
        <div className="result__scroll">
          <table className="grid grid--compact">
            <thead>
              <tr>
                <th scope="col">column</th>
                <th scope="col">type</th>
                <th scope="col">null</th>
              </tr>
            </thead>
            <tbody>
              {described.columns.map((column) => (
                <tr key={column.name}>
                  <td>{column.name}</td>
                  <td className="is-muted">{column.type}</td>
                  <td className="is-muted">{column.nullable ? 'yes' : 'no'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {described.primary_key.length > 0 && (
          <p className="schema__line">
            <span className="schema__key">primary key</span>
            {described.primary_key.join(', ')}
          </p>
        )}
        {described.foreign_keys.map((fk, index) => (
          <p className="schema__line" key={`${fk.referred_table}-${index}`}>
            <span className="schema__key">foreign key</span>
            {fk.columns.join(', ')} → {fk.referred_table}({fk.referred_columns.join(', ')})
          </p>
        ))}
      </div>
    );
  }

  return (
    <div className="schema__entry">
      <span className="schema__tool mono-code">{result.tool_name}</span>
      <pre className="schema__raw">{JSON.stringify(result.data, null, 2)}</pre>
    </div>
  );
}

export const SchemaDetails = memo(function SchemaDetails({
  results,
}: {
  results: SchemaToolResult[];
}) {
  if (!results.length) return null;

  return (
    <div className="schema">
      {results.map((result) => (
        <SchemaEntry key={result.tool_call_id} result={result} />
      ))}
    </div>
  );
});
