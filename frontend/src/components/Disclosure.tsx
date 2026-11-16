import { useId, useState, type ReactNode } from 'react';
import { IconChevron } from './icons';

interface DisclosureProps {
  label: string;
  meta?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * A section that can be folded away. Used for the SQL trace, the schema trace
 * and the metadata row of an answer.
 */
export function Disclosure({ label, meta, defaultOpen = false, children }: DisclosureProps) {
  const [openOverride, setOpenOverride] = useState<boolean | null>(null);
  const open = openOverride ?? defaultOpen;
  const regionId = useId();

  return (
    <section className={`disc${open ? ' is-open' : ''}`}>
      <button
        type="button"
        className="disc__head"
        onClick={() => setOpenOverride(!open)}
        aria-expanded={open}
        aria-controls={regionId}
      >
        <IconChevron size={14} className="disc__chevron" />
        <span className="disc__label mono-label">{label}</span>
        {meta ? <span className="disc__meta">{meta}</span> : null}
      </button>
      <div className="disc__body" id={regionId} hidden={!open}>
        {open && <div className="disc__inner">{children}</div>}
      </div>
    </section>
  );
}
