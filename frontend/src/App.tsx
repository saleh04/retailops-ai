import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, analyze, getConversation } from './api/client';
import { ChatView } from './components/ChatView';
import { ConnectScreen } from './components/ConnectScreen';
import { ConnectionPanel } from './components/ConnectionPanel';
import { Sidebar } from './components/Sidebar';
import { useConnection } from './hooks/useConnection';
import { useConversations } from './hooks/useConversations';
import { useTheme } from './hooks/useTheme';
import {
  analysisErrorMessage,
  connectErrorMessage,
  conversationErrorMessage,
} from './lib/errors';
import { localId, turnFromMessage, type Turn } from './lib/thread';

export default function App() {
  const { theme, toggle } = useTheme();
  const {
    connection,
    loading: connectionLoading,
    busy,
    offline,
    refresh,
    connect,
    disconnect,
  } = useConnection();

  const connected = connection.status === 'connected';
  const connectionId = connection.connection_id;

  const {
    items: conversations,
    loading: conversationsLoading,
    error: conversationsError,
    reload: reloadConversations,
    remove: removeConversation,
  } = useConversations(connectionId);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [loadedTitle, setLoadedTitle] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [composerError, setComposerError] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [disconnectError, setDisconnectError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const historyRequest = useRef(0);

  // A different database means a different set of conversations.
  useEffect(() => {
    historyRequest.current += 1;
    setTurns([]);
    setActiveConversationId(null);
    setLoadedTitle(null);
    setComposerError(null);
    setLoadingHistory(false);
  }, [connectionId]);

  const title = useMemo(() => {
    const fromList = conversations.find((item) => item.id === activeConversationId)?.title;
    return fromList ?? loadedTitle;
  }, [conversations, activeConversationId, loadedTitle]);

  const handleConnect = useCallback(
    async (databaseUrl: string) => {
      setConnectError(null);
      const result = await connect(databaseUrl);
      if (!result.ok) {
        setConnectError(result.error ?? connectErrorMessage(result));
        return false;
      }
      setTurns([]);
      setActiveConversationId(null);
      setLoadedTitle(null);
      setComposerError(null);
      setPanelOpen(false);
      return true;
    },
    [connect],
  );

  const handleDisconnect = useCallback(async () => {
    setDisconnectError(null);
    const result = await disconnect();
    if (!result.ok) {
      setDisconnectError(result.error ?? 'The connection could not be closed.');
      return;
    }
    setPanelOpen(false);
    setTurns([]);
    setActiveConversationId(null);
    setLoadedTitle(null);
  }, [disconnect]);

  const handleSelectConversation = useCallback(async (id: string) => {
    const requestId = ++historyRequest.current;
    setLoadingHistory(true);
    setComposerError(null);
    try {
      const detail = await getConversation(id);
      if (requestId !== historyRequest.current) return;
      setTurns(detail.messages.map(turnFromMessage));
      setActiveConversationId(detail.id);
      setLoadedTitle(detail.title);
    } catch (error) {
      if (requestId === historyRequest.current) {
        setComposerError(conversationErrorMessage(error));
      }
    } finally {
      if (requestId === historyRequest.current) {
        setLoadingHistory(false);
      }
    }
  }, []);

  const handleNewConversation = useCallback(() => {
    historyRequest.current += 1;
    setLoadingHistory(false);
    setTurns([]);
    setActiveConversationId(null);
    setLoadedTitle(null);
    setComposerError(null);
  }, []);

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      const result = await removeConversation(id);
      if (!result.ok) {
        setComposerError(result.error ?? 'The conversation could not be deleted.');
        return;
      }
      if (id === activeConversationId) {
        historyRequest.current += 1;
        setLoadingHistory(false);
        setTurns([]);
        setActiveConversationId(null);
        setLoadedTitle(null);
      }
    },
    [removeConversation, activeConversationId],
  );

  const handleAsk = useCallback(
    async (question: string) => {
      if (pending) return;
      setComposerError(null);

      const userTurn: Turn = {
        id: localId('user'),
        role: 'user',
        content: question,
        createdAt: new Date().toISOString(),
      };
      setTurns((current) => [...current, userTurn]);
      setPending(true);

      try {
        const response = await analyze(question, activeConversationId);

        const assistantTurn: Turn = {
          id: localId('assistant'),
          role: 'assistant',
          content: response.answer,
          status: response.status,
          queries: response.queries ?? [],
          schemaResults: response.schema_results ?? [],
          metadata: response.metadata ?? null,
          error: response.error,
          createdAt: new Date().toISOString(),
        };
        setTurns((current) => [...current, assistantTurn]);

        if (response.conversation_id && response.conversation_id !== activeConversationId) {
          setActiveConversationId(response.conversation_id);
          setLoadedTitle((current) => current ?? question);
        }

        // Refresh so message counts and the ordering stay accurate, whether
        // this turn started a conversation or continued an existing one.
        void reloadConversations();
      } catch (error) {
        setComposerError(analysisErrorMessage(error));
        if (error instanceof ApiError && error.status === 404) {
          // The conversation no longer belongs to this connection.
          setActiveConversationId(null);
          setLoadedTitle(null);
        }
        if (error instanceof ApiError && error.status === 409) {
          void refresh();
        }
      } finally {
        setPending(false);
      }
    },
    [pending, activeConversationId, reloadConversations, refresh],
  );

  return (
    <div className={`app${sidebarCollapsed ? ' app--sidebar-collapsed' : ''}`}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <Sidebar
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onCollapse={() => setSidebarCollapsed(true)}
        connection={connection}
        connectionLoading={connectionLoading}
        conversations={conversations}
        conversationsLoading={conversationsLoading}
        conversationsError={conversationsError}
        activeConversationId={activeConversationId}
        onSelectConversation={(id) => void handleSelectConversation(id)}
        onNewConversation={handleNewConversation}
        onDeleteConversation={(id) => void handleDeleteConversation(id)}
        interactionDisabled={pending || loadingHistory}
        onOpenConnection={() => setPanelOpen(true)}
        theme={theme}
        onToggleTheme={toggle}
      />

      <main className="main" id="main">
        {offline && (
          <p className="offline" role="status">
            The RetailOps AI API is not responding. Start the backend on port 5000 and reload.
          </p>
        )}

        {connected ? (
          <ChatView
            turns={turns}
            pending={pending}
            loadingHistory={loadingHistory}
            composerError={composerError}
            title={title}
            connection={connection}
            sidebarCollapsed={sidebarCollapsed}
            navigationOpen={drawerOpen}
            onAsk={(question) => void handleAsk(question)}
            onNewConversation={handleNewConversation}
            onOpenNavigation={() => {
              if (window.matchMedia('(max-width: 960px)').matches) {
                setDrawerOpen(true);
              } else {
                setSidebarCollapsed(false);
              }
            }}
          />
        ) : (
          connectionLoading ? (
            <p className="connection-loading" role="status">
              Checking database connection…
            </p>
          ) : (
            <ConnectScreen
              onConnect={handleConnect}
              busy={busy}
              error={connectError}
              offline={offline}
            />
          )
        )}
      </main>

      <ConnectionPanel
        open={panelOpen}
        connection={connection}
        busy={busy}
        connectError={connectError}
        disconnectError={disconnectError}
        onClose={() => setPanelOpen(false)}
        onConnect={handleConnect}
        onDisconnect={() => void handleDisconnect()}
      />
    </div>
  );
}
