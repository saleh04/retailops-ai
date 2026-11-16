import { useState, type FormEvent } from 'react';
import { IconAlert } from './icons';

const SCHEMES = [
  { name: 'SQLite', url: 'sqlite:///absolute/path/to/file.db' },
  { name: 'PostgreSQL', url: 'postgresql://user:password@host:5432/database' },
  { name: 'MySQL', url: 'mysql+pymysql://user:password@host:3306/database' },
  {
    name: 'SQL Server (Windows authentication)',
    url: 'mssql+pyodbc://@DESKTOP-SIMEL6O/AdventureWorks2022?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes',
  },
  {
    name: 'SQL Server (username/password)',
    url: 'mssql+pyodbc://user:password@host:1433/database?driver=ODBC+Driver+17+for+SQL+Server',
  },
];

interface ConnectionFormProps {
  onConnect: (databaseUrl: string) => Promise<boolean>;
  busy: boolean;
  error: string | null;
  idPrefix?: string;
}

export function ConnectionForm({
  onConnect,
  busy,
  error,
  idPrefix = 'conn',
}: ConnectionFormProps) {
  const [url, setUrl] = useState('');

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const value = url.trim();
    if (!value || busy) return;
    const ok = await onConnect(value);
    if (ok) setUrl('');
  }

  return (
    <form className="connform" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <label className="field__label" htmlFor={`${idPrefix}-url`}>
          Database URL
        </label>
        <input
          id={`${idPrefix}-url`}
          className="input"
          type="text"
          inputMode="url"
          spellCheck={false}
          autoComplete="off"
          placeholder="mssql+pyodbc://@SERVER/DATABASE?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          disabled={busy}
          aria-describedby={`${idPrefix}-url-hint`}
          aria-invalid={Boolean(error)}
        />
        <p className="connform__hint" id={`${idPrefix}-url-hint`}>
          The URL is sent to the backend and not stored in the browser. Windows trusted
          connections use the Windows account running the backend.
        </p>
      </div>

      {error && (
        <p className="notice notice--bad" role="alert">
          <IconAlert size={16} className="notice__icon" />
          <span>{error}</span>
        </p>
      )}

      <div className="connform__actions">
        <button
          type="submit"
          className="btn btn--primary connform__submit"
          disabled={busy || !url.trim()}
        >
          {busy ? 'Connecting…' : 'Connect'}
        </button>
      </div>

      <div className="connform__schemes">
        <span className="caption">Accepted URL schemes</span>
        <ul>
          {SCHEMES.map((item) => (
            <li key={item.name}>
              <span>{item.name}</span>
              <code>{item.url}</code>
            </li>
          ))}
        </ul>
      </div>
    </form>
  );
}

export function ConnectionStatusBlock({
  connected,
  dialectLabel,
  connectionId,
  onDisconnect,
  busy,
  error,
}: {
  connected: boolean;
  dialectLabel: string;
  connectionId: string | null;
  onDisconnect: () => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <div className="connstatus">
      <div className="connstatus__row">
        <span className={`connstate__dot${connected ? ' is-on' : ''}`} aria-hidden="true" />
        <div>
          <p className="connstatus__state">
            {connected ? 'Connected' : 'Not connected'}
            {connected && <span className="connstatus__type">{dialectLabel}</span>}
          </p>
          <p className="connstatus__meta">
            {connected
              ? `connection id ${connectionId ?? 'unknown'}`
              : 'Ask questions once a database is connected.'}
          </p>
        </div>
      </div>

      {error && (
        <p className="notice notice--bad" role="alert">
          <IconAlert size={16} className="notice__icon" />
          <span>{error}</span>
        </p>
      )}

      {connected && (
        <button
          type="button"
          className="btn btn--danger connstatus__disconnect"
          onClick={onDisconnect}
          disabled={busy}
        >
          {busy ? 'Disconnecting…' : 'Disconnect database'}
        </button>
      )}
    </div>
  );
}
