import { useEffect, useRef } from 'react';
import type { ConnectionResponse } from '../api/types';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { getDialect } from '../lib/dialects';
import { ConnectionForm, ConnectionStatusBlock } from './ConnectionForm';
import { IconClose } from './icons';

interface ConnectionPanelProps {
  open: boolean;
  connection: ConnectionResponse;
  busy: boolean;
  connectError: string | null;
  disconnectError: string | null;
  onClose: () => void;
  onConnect: (databaseUrl: string) => Promise<boolean>;
  onDisconnect: () => void;
}

export function ConnectionPanel({
  open,
  connection,
  busy,
  connectError,
  disconnectError,
  onClose,
  onConnect,
  onDisconnect,
}: ConnectionPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const connected = connection.status === 'connected';
  const dialect = getDialect(connection.dialect);

  useFocusTrap(panelRef, open, onClose);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="sheet">
      <button
        type="button"
        className="sheet__scrim"
        onClick={onClose}
        aria-label="Close database connection panel"
      />

      <div
        className="sheet__panel"
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="connection-panel-title"
      >
        <header className="sheet__head">
          <h2 className="sheet__title" id="connection-panel-title">
            Database connection
          </h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close panel">
            <IconClose size={17} />
          </button>
        </header>

        <div className="sheet__body">
          <ConnectionStatusBlock
            connected={connected}
            dialectLabel={dialect.label}
            connectionId={connection.connection_id}
            onDisconnect={onDisconnect}
            busy={busy}
            error={disconnectError}
          />

          <div className="sheet__divider">
            <span className="caption">Connect a database</span>
          </div>

          <ConnectionForm
            onConnect={onConnect}
            busy={busy}
            error={connectError}
            idPrefix="sheet"
          />
        </div>
      </div>
    </div>
  );
}
