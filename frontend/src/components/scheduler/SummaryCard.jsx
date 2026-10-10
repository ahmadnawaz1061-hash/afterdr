import { Activity } from 'lucide-react';
import Card from '../common/Card';
import { formatTime } from './schedulerUtils';

export default function SummaryCard({ total, taken, nextDose }) {
  const progress = total ? Math.round((taken / total) * 100) : 0;
  return (
    <Card title="Today's progress" titleId="schedule-summary-title" icon={Activity}>
      <div className="flex items-end justify-between gap-4">
        <p className="text-2xl font-bold text-slate-950">{taken} of {total} taken today</p>
        <p className="shrink-0 text-sm font-semibold text-teal-800">{progress}%</p>
      </div>
      <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-label="Today's doses taken" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progress}>
        <div className="h-full rounded-full bg-teal-700 transition-[width]" style={{ width: `${progress}%` }} />
      </div>
      <p className="mt-4 text-sm font-semibold text-slate-800">Next dose: {nextDose ? formatTime(nextDose.local_time) : 'None scheduled'}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">Reminders work only while this page is open in your browser.</p>
    </Card>
  );
}
