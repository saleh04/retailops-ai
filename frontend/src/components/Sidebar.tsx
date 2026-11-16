import { useEffect, useRef, useState } from 'react';
import type { ConnectionResponse, ConversationSummary } from '../api/types';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { getDialect } from '../lib/dialects';
import { formatTimestamp } from '../lib/format';
import { IconChevron, IconDatabase, IconMoon, IconPlus, IconSun, IconTrash } from './icons';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  onCollapse: () => void;
  connection: ConnectionResponse;
  connectionLoading: boolean;
  conversations: ConversationSummary[];
  conversationsLoading: boolean;
  conversationsError: string | null;
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (id: string) => void;
  interactionDisabled: boolean;
  onOpenConnection: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}

function Wordmark() {
  return (
    <div className="brand">
      <span className="brand__mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="30" height="30">
          <rect width="32" height="32" rx="8" fill="currentColor" />
          <rect x="7" y="18" width="4" height="7" rx="1.2" fill="var(--surface)" />
          <rect x="14" y="13" width="4" height="12" rx="1.2" fill="var(--surface)" />
          <rect x="21" y="8" width="4" height="17" rx="1.2" fill="var(--surface)" />
        </svg>
      </span>
      <span className="brand__text">
        <span className="brand__name">RetailOps</span>
        <span className="brand__suffix mono-label">AI</span>
      </span>
    </div>
  );
}

export function Sidebar({
  open,
  onClose,
  onCollapse,
  connection,
  connectionLoading,
  conversations,
  conversationsLoading,
  conversationsError,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  interactionDisabled,
  onOpenConnection,
  theme,
  onToggleTheme,
}: SidebarProps) {
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const connected = connection.status === 'connected';
  const dialect = getDialect(connection.dialect);

  // On small screens the sidebar is an overlay drawer: focus stays inside it
  // until it is dismissed, and Escape closes it.
  useFocusTrap(sidebarRef, open, onClose);

  useEffect(() => {
    if (open) closeButtonRef.current?.focus();
  }, [open]);

  return (
    <>
      <button
        type="button"
        className={`scrim${open ? ' is-open' : ''}`}
        onClick={onClose}
        aria-label="Close navigation"
        tabIndex={open ? 0 : -1}
      />

      <aside
        className={`sidebar${open ? ' is-open' : ''}`}
        aria-label="Conversations and connection"
        ref={sidebarRef}
      >
        <div className="sidebar__head">
          <Wordmark />
          <button
            type="button"
            className="icon-btn sidebar__collapse"
            onClick={onCollapse}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
          >
            <IconChevron size={16} className="sidebar__collapse-icon" />
          </button>
          <button
            type="button"
            className="icon-btn sidebar__close"
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Close navigation"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="sidebar__actions">
          <button
            type="button"
            className="btn btn--primary sidebar__new"
            disabled={interactionDisabled}
            onClick={() => {
              onNewConversation();
              onClose();
            }}
          >
            <IconPlus size={15} />
            New conversation
          </button>
        </div>

        <div className="sidebar__section">
          <div className="sidebar__section-head">
            <span className="caption">Conversations</span>
            {conversations.length > 0 && (
              <span className="sidebar__count">{conversations.length}</span>
            )}
          </div>

          <div className="sidebar__list">
            {conversationsLoading && conversations.length === 0 && (
              <p className="sidebar__placeholder">Loading conversations…</p>
            )}

            {conversationsError && (
              <p className="sidebar__placeholder sidebar__placeholder--error">{conversationsError}</p>
            )}

            {!conversationsLoading && !conversationsError && conversations.length === 0 && (
              <p className="sidebar__placeholder">
                No conversations yet. Ask a question to start one.
              </p>
            )}

            <ul className="threads">
              {conversations.map((conversation) => {
                const active = conversation.id === activeConversationId;
                const confirming = confirmingId === conversation.id;

                return (
                  <li key={conversation.id}>
                    {confirming ? (
                      <div className="thread thread--confirming">
                        <p className="thread__confirm-text">Delete this conversation?</p>
                        <div className="thread__confirm-actions">
                          <button
                            type="button"
                            className="btn btn--sm btn--danger"
                            onClick={() => {
                              setConfirmingId(null);
                              onDeleteConversation(conversation.id);
                            }}
                          >
                            Delete
                          </button>
                          <button
                            type="button"
                            className="btn btn--sm btn--ghost"
                            onClick={() => setConfirmingId(null)}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className={`thread${active ? ' is-active' : ''}`}>
                        <button
                          type="button"
                          className="thread__open"
                          disabled={interactionDisabled}
                          onClick={() => {
                            onSelectConversation(conversation.id);
                            onClose();
                          }}
                          aria-current={active ? 'true' : undefined}
                        >
                          <span className="thread__title">
                            {conversation.title ?? 'Untitled conversation'}
                          </span>
                          <span className="thread__meta">
                            {conversation.message_count}{' '}
                            {conversation.message_count === 1 ? 'message' : 'messages'}
                            <span className="thread__sep">·</span>
                            {formatTimestamp(conversation.updated_at)}
                          </span>
                        </button>
                        <button
                          type="button"
                          className="icon-btn icon-btn--sm thread__delete"
                          disabled={interactionDisabled}
                          onClick={() => setConfirmingId(conversation.id)}
                          aria-label={`Delete conversation: ${conversation.title ?? 'Untitled conversation'}`}
                          title="Delete conversation"
                        >
                          <IconTrash size={14} />
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <div className="sidebar__foot">
          <div className={`connstate${connected ? ' is-on' : ''}`}>
            <span className="connstate__dot" aria-hidden="true" />
            <div className="connstate__body">
              <p className="connstate__title">
                  {connectionLoading
                    ? 'Checking database connection…'
                    : connected
                      ? `Connected · ${dialect.label}`
                      : 'No database connected'}
              </p>
              <p className="connstate__meta">
                  {connectionLoading
                    ? 'Contacting the RetailOps AI API'
                    : connected
                  ? `connection ${connection.connection_id?.slice(0, 8) ?? ''}`
                  : 'Connect a database to start asking questions'}
              </p>
            </div>
          </div>

          <div className="sidebar__foot-row">
            <button
              type="button"
              className="btn btn--sm sidebar__connection-btn"
              disabled={interactionDisabled}
              onClick={onOpenConnection}
            >
              <IconDatabase size={14} />
              Database connection
            </button>
            <button
              type="button"
              className="icon-btn"
              onClick={onToggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {theme === 'dark' ? <IconSun size={16} /> : <IconMoon size={16} />}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
