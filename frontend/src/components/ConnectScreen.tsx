import { ConnectionForm } from './ConnectionForm';
import { IconAlert, IconDatabase } from './icons';

interface ConnectScreenProps {
  onConnect: (databaseUrl: string) => Promise<boolean>;
  busy: boolean;
  error: string | null;
  offline: boolean;
}

const GUARANTEES = [
  {
    key: 'Read-only',
    text: 'Every statement is parsed and rejected unless it is a single read-only query.',
  },
  {
    key: 'Row-capped',
    text: 'Result sets are capped server-side, and a truncated result says so.',
  },
  {
    key: 'Traceable',
    text: 'Every answer ships with the SQL that produced it and the rows it returned.',
  },
];

export function ConnectScreen({ onConnect, busy, error, offline }: ConnectScreenProps) {
  return (
    <div className="connect">
      <div className="connect__inner">
        <section className="connect__pitch">
          <span className="connect__glyph" aria-hidden="true">
            <IconDatabase size={20} />
          </span>

          <h1 className="connect__title">Connect your retail database</h1>
          <p className="connect__lede">
            RetailOps AI reads the schema, writes read-only SQL, and answers with the rows behind
            the number — so every figure you get is traceable to a statement you can inspect.
          </p>

          <ul className="connect__facts">
            {GUARANTEES.map((item) => (
              <li key={item.key}>
                <span className="connect__fact-key caption">{item.key}</span>
                <span className="connect__fact-text">{item.text}</span>
              </li>
            ))}
          </ul>
        </section>

        <div className="connect__panel">
          {offline && (
            <p className="notice notice--warn" role="alert">
              <IconAlert size={16} className="notice__icon" />
              <span>
                The backend at <code>http://localhost:5000</code> is not responding. Start it,
                then retry.
              </span>
            </p>
          )}

          <div className="connect__card">
            <ConnectionForm onConnect={onConnect} busy={busy} error={error} idPrefix="connect" />
          </div>

          <p className="connect__footnote">
            A local SQLite file works too — point the URL at the bundled sample database:
          </p>
          <p className="connect__footnote connect__footnote--code">
            <code>sqlite:///absolute/path/to/retailops-ai/data/olist.db</code>
          </p>
        </div>
      </div>
    </div>
  );
}
