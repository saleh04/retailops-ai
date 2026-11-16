import type { AnalysisStatus } from '../api/types';
import { IconAlert, IconCheck, IconInbox } from './icons';

const STATE_META: Record<
  AnalysisStatus,
  { label: string; tone: 'ok' | 'warn' | 'bad'; Icon: typeof IconCheck }
> = {
  success: { label: 'Answered', tone: 'ok', Icon: IconCheck },
  no_data: { label: 'No data', tone: 'warn', Icon: IconInbox },
  failed: { label: 'Failed', tone: 'bad', Icon: IconAlert },
};

export function StatusBadge({ status }: { status: AnalysisStatus }) {
  const { label, tone, Icon } = STATE_META[status];
  return (
    <span className={`status status--${tone}`}>
      <Icon size={13} />
      {label}
    </span>
  );
}
