import { CalendarClock } from 'lucide-react';
import { Link } from 'react-router-dom';
import Card from '../common/Card';

export function EmptyScheduleCard() {
  return (
    <Card title="No schedule yet" titleId="empty-schedule-title" icon={CalendarClock}>
      <p className="text-sm leading-6 text-slate-600">Confirm a reviewed prescription before creating medicine reminders.</p>
      <Link to="/prescription" className="button-secondary mt-5">Go to Prescription Reader</Link>
    </Card>
  );
}

export function SchedulerSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading your schedule">
      {[0, 1, 2].map((value) => <div key={value} className="animate-pulse rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:p-5"><div className="flex gap-3"><div className="size-10 rounded-xl bg-slate-200" /><div className="flex-1"><div className="h-4 w-2/5 rounded bg-slate-200" /><div className="mt-3 h-3 w-4/5 rounded bg-slate-100" /></div></div><div className="mt-5 h-20 rounded-xl bg-slate-100" /></div>)}
      <span className="sr-only">Loading your schedule…</span>
    </div>
  );
}
