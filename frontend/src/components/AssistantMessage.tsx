import { memo } from 'react';
import type { AnalysisMetadata, AnalysisStatus, SchemaToolResult, SQLExecutionResult } from '../api/types';
import { Markdown } from '../lib/Markdown';
import { getDialect } from '../lib/dialects';
import { formatTime } from '../lib/format';
import { Disclosure } from './Disclosure';
import { IconAlert, IconCheck, IconInbox } from './icons';
import { ResultTable } from './ResultTable';
import { SchemaDetails } from './SchemaDetails';
import { SqlBlock } from './SqlBlock';

interface AssistantMessageProps {
  status: AnalysisStatus;
  content: string | null;
  queries: SQLExecutionResult[];
  schemaResults: SchemaToolResult[];
  metadata: AnalysisMetadata | null;
  error: string | null;
  createdAt: string;
}

const BAND: Record<AnalysisStatus, { title: string; Icon: typeof IconCheck }> = {
  success: { title: 'Answer', Icon: IconCheck },
  no_data: { title: 'No matching rows', Icon: IconInbox },
  failed: { title: 'Analysis failed', Icon: IconAlert },
};

export const AssistantMessage = memo(function AssistantMessage({
  status,
  content,
  queries,
  schemaResults,
  metadata,
  error,
  createdAt,
}: AssistantMessageProps) {
  const { title, Icon } = BAND[status];
  const dialect = getDialect(metadata?.dialect);
  const toolCount = metadata?.tools_used?.length ?? 0;
  const resultQueries = queries.filter((query) => query.data !== null);
  const truncated = resultQueries.some((query) => query.data?.truncated);

  return (
    <article className={`answer answer--${status}`}>
      <header className="answer__band">
        <Icon size={15} className="answer__band-icon" />
        <h2 className="answer__band-title">{title}</h2>
        <span className="answer__band-meta">
          {dialect.label.toLowerCase()}
          {toolCount > 0 && ` · ${toolCount} tool ${toolCount === 1 ? 'call' : 'calls'}`}
          {formatTime(createdAt) && ` · ${formatTime(createdAt)}`}
        </span>
      </header>

      <div className="answer__content">
        {status === 'failed' ? (
          <div className="answer__failure">
            <p className="answer__failure-text">{error ?? 'The analysis could not be completed.'}</p>
            <p className="answer__failure-hint">
              The turn was still saved to this conversation. Rephrase the question or narrow it
              down and ask again.
            </p>
          </div>
        ) : (
          <>
            {content ? (
              <div className="answer__prose">
                <Markdown text={content} />
              </div>
            ) : null}

            {status === 'no_data' && (
              <p className="answer__hint">
                <IconInbox size={14} className="answer__hint-icon" />
                <span>
                  The statements ran, but nothing matched. Widen the filters or ask about a
                  different slice of the data.
                </span>
              </p>
            )}
          </>
        )}

        <div className="answer__sections">
          {queries.length > 0 && (
            <Disclosure
              label="SQL queries"
              meta={
                <>
                  {queries.length} {queries.length === 1 ? 'query' : 'queries'}
                  {queries.some((query) => query.status === 'failed') && ' · one failed'}
                </>
              }
            >
              <div className="answer__stack">
                {queries.map((query, index) => (
                  <SqlBlock query={query} index={index} key={query.tool_call_id} />
                ))}
              </div>
            </Disclosure>
          )}

          {resultQueries.length > 0 && (
            <Disclosure
              label="Query results"
              meta={
                <>
                  {resultQueries.length} {resultQueries.length === 1 ? 'result set' : 'result sets'}
                  {truncated && ' · truncated'}
                </>
              }
            >
              <div className="answer__stack">
                {resultQueries.map((query) => (
                  <ResultTable
                    query={query}
                    index={queries.indexOf(query)}
                    key={query.tool_call_id}
                  />
                ))}
              </div>
            </Disclosure>
          )}

          {schemaResults.length > 0 && (
            <Disclosure
              label="Schema inspected"
              meta={`${schemaResults.length} ${schemaResults.length === 1 ? 'lookup' : 'lookups'}`}
            >
              <SchemaDetails results={schemaResults} />
            </Disclosure>
          )}

          {metadata && metadata.tools_used.length > 0 && (
            <Disclosure label="Run metadata" meta={metadata.dialect}>
              <div className="answer__stack">
                <div className="metadata">
                  <span className="metadata__key caption caption--dim">Dialect</span>
                  <span className="tag tag--accent">{metadata.dialect}</span>
                </div>
                <div className="metadata">
                  <span className="metadata__key caption caption--dim">Tools used</span>
                  <div className="metadata__tags">
                    {metadata.tools_used.map((tool, index) => (
                      <span className="tag" key={`${tool}-${index}`}>
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </Disclosure>
          )}
        </div>
      </div>
    </article>
  );
});
