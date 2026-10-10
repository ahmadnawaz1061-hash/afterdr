import { Bell, BellRing, Check, Clock3, X } from 'lucide-react';
import Card from '../common/Card';
import { formatTime } from './schedulerUtils';

export function ReminderBannerCard({ dose, onTaken, onSnooze, onSkip }) {
  if (!dose) return null;
  return (
    <Card title={`Time for ${dose.medicine_name} (${formatTime(dose.local_time)})`} titleId="due-reminder-title" icon={BellRing} className="scheduler-reminder-enter border-teal-400 bg-teal-50 shadow-md" role="alert" aria-live="assertive" footer={(
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <button type="button" onClick={onTaken} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-teal-800 px-4 text-sm font-bold text-white hover:bg-teal-900"><Check size={18} aria-hidden="true" />Taken</button>
        <button type="button" onClick={onSnooze} className="button-secondary gap-2"><Clock3 size={18} aria-hidden="true" />Snooze 10 min</button>
        <button type="button" onClick={onSkip} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-bold text-rose-800 hover:bg-rose-50"><X size={18} aria-hidden="true" />Skip</button>
      </div>
    )}>
      <p className="text-sm text-slate-700">{dose.dose || 'Follow your reviewed prescription instructions.'}</p>
    </Card>
  );
}

export function TurnOnRemindersCard({ onEnable }) {
  return (
    <Card title="Turn on reminders" titleId="turn-on-reminders-title" icon={Bell} footer={<button type="button" onClick={onEnable} className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-teal-800 px-5 text-sm font-bold text-white hover:bg-teal-900 sm:w-auto"><Bell size={18} aria-hidden="true" />Turn on reminders</button>}>
      <p className="text-sm leading-6 text-slate-600">Allow browser notifications to receive a prompt when a dose is due. Keep this page open for reminders to work.</p>
    </Card>
  );
}
