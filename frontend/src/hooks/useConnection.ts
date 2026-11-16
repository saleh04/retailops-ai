import { useCallback, useEffect, useState } from 'react';
import {
  createConnection,
  deleteConnection,
  getConnection,
  type ConnectionResponse,
} from '../api/client';
import { connectErrorMessage, disconnectErrorMessage } from '../lib/errors';

const DISCONNECTED: ConnectionResponse = {
  status: 'disconnected',
  dialect: null,
  connection_id: null,
};

export interface ActionResult {
  ok: boolean;
  error?: string;
}

export function useConnection() {
  const [connection, setConnection] = useState<ConnectionResponse>(DISCONNECTED);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const next = await getConnection();
      setConnection(next);
      setOffline(false);
    } catch {
      setOffline(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const connect = useCallback(async (databaseUrl: string): Promise<ActionResult> => {
    setBusy(true);
    try {
      const next = await createConnection(databaseUrl);
      setConnection(next);
      setOffline(false);
      return { ok: true };
    } catch (error) {
      return { ok: false, error: connectErrorMessage(error) };
    } finally {
      setBusy(false);
    }
  }, []);

  const disconnect = useCallback(async (): Promise<ActionResult> => {
    setBusy(true);
    try {
      await deleteConnection();
      setConnection(DISCONNECTED);
      return { ok: true };
    } catch (error) {
      return { ok: false, error: disconnectErrorMessage(error) };
    } finally {
      setBusy(false);
    }
  }, []);

  return { connection, loading, busy, offline, refresh, connect, disconnect };
}
