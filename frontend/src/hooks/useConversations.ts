import { useCallback, useEffect, useState } from 'react';
import { deleteConversation, listConversations, type ConversationSummary } from '../api/client';
import { conversationErrorMessage } from '../lib/errors';

export function useConversations(connectionId: string | null) {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!connectionId) {
      setItems([]);
      setError(null);
      return;
    }
    setLoading(true);
    try {
      const next = await listConversations(connectionId);
      setItems(next);
      setError(null);
    } catch (caught) {
      setError(conversationErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [connectionId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const remove = useCallback(
    async (id: string): Promise<ActionResult> => {
      try {
        await deleteConversation(id);
        setItems((current) => current.filter((item) => item.id !== id));
        return { ok: true };
      } catch (caught) {
        return { ok: false, error: conversationErrorMessage(caught) };
      }
    },
    [],
  );

  return { items, loading, error, reload, remove };
}

export interface ActionResult {
  ok: boolean;
  error?: string;
}
