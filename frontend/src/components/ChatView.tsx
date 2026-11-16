import { useEffect, useRef } from 'react';
import type { ConnectionResponse } from '../api/types';
import { getDialect } from '../lib/dialects';
import type { Turn } from '../lib/thread';
import { AssistantMessage } from './AssistantMessage';
import { Composer } from './Composer';
import { IconMenu, IconPlus } from './icons';

interface ChatViewProps {
  turns: Turn[];
  pending: boolean;
  loadingHistory: boolean;
  composerError: string | null;
  title: string | null;
  connection: ConnectionResponse;
  sidebarCollapsed: boolean;
  navigationOpen: boolean;
  onAsk: (question: string) => void;
  onNewConversation: () => void;
  onOpenNavigation: () => void;
}

export function ChatView({
  turns,
  pending,
  loadingHistory,
  composerError,
  title,
  connection,
  sidebarCollapsed,
  navigationOpen,
  onAsk,
  onNewConversation,
  onOpenNavigation,
}: ChatViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const dialect = getDialect(connection.dialect);
  let turnCount = 0;
  for (const turn of turns) {
    if (turn.role === 'assistant') turnCount += 1;
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns.length, pending]);

  useEffect(() => {
    if (sidebarCollapsed) menuButtonRef.current?.focus();
  }, [sidebarCollapsed]);

  return (
    <section className="chat" aria-label="Analysis">
      <header className="topbar">
        <button
          type="button"
          className="icon-btn topbar__menu"
          ref={menuButtonRef}
          onClick={onOpenNavigation}
          aria-label="Open navigation"
          aria-expanded={navigationOpen}
        >
          <IconMenu size={18} />
        </button>

        <div className="topbar__heading">
          <h1 className="topbar__title">{title ?? 'New conversation'}</h1>
          <p className="topbar__meta">
            {dialect.label}
            {turnCount > 0 && ` · ${turnCount} ${turnCount === 1 ? 'answer' : 'answers'}`}
          </p>
        </div>

        <div className="topbar__actions">
          <button
            type="button"
            className="btn btn--sm topbar__new"
            onClick={onNewConversation}
            disabled={pending || loadingHistory}
          >
            <IconPlus size={14} />
            New
          </button>
        </div>
      </header>

      <div className="thread-scroll" ref={scrollRef}>
        <div className="thread-inner">
          {loadingHistory && (
            <p className="thread-loading" role="status">
              Loading conversation…
            </p>
          )}

          {turns.length === 0 && !pending && !loadingHistory && (
            <div className="empty-thread">
              <h2 className="empty-thread__title">Ask a question about your data</h2>
              <p className="empty-thread__lede">
                Explore the connected database in natural language. Answers include the SQL and
                returned rows.
              </p>
            </div>
          )}

          {turns.map((turn) =>
            turn.role === 'user' ? (
              <div className="ask" key={turn.id}>
                <span className="ask__label">
                  <span className="ask__mark" aria-hidden="true" />
                  <span className="caption caption--dim">You asked</span>
                </span>
                <p className="ask__text">{turn.content}</p>
              </div>
            ) : (
              <AssistantMessage
                key={turn.id}
                status={turn.status}
                content={turn.content}
                queries={turn.queries}
                schemaResults={turn.schemaResults}
                metadata={turn.metadata}
                error={turn.error}
                createdAt={turn.createdAt}
              />
            ),
          )}

          {pending && (
            <div className="pending" role="status" aria-live="polite">
              <div className="pending__bar" aria-hidden="true">
                <span />
              </div>
              <p className="pending__text">
                Inspecting the schema, writing SQL and running the statement…
              </p>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <Composer
        onSubmit={onAsk}
        pending={pending}
        disabled={loadingHistory}
        error={composerError}
      />
    </section>
  );
}
