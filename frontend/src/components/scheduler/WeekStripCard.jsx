import { CalendarDays } from 'lucide-react';
import Card from '../common/Card';
import { dateAtOffset } from './schedulerUtils';

export default function WeekStripCard({ selectedDay, onSelectDay }) {
  const days = Array.from({ length: 7 }, (_, offset) => {
    const date = dateAtOffset(offset);
    const parsed = new Date(`${date}T12:00:00`);
    return {
      date,
      weekday: new Intl.DateTimeFormat('en-US', { weekday: 'short' }).format(parsed),
      number: parsed.getDate(),
      today: offset === 0,
    };
  });

  return (
    <Card title="Choose a day" titleId="week-strip-title" icon={CalendarDays}>
      <div className="grid grid-cols-7 gap-1.5" role="group" aria-label="Schedule days">
        {days.map((day) => (
          <button
            key={day.date}
            type="button"
            onClick={() => onSelectDay(day.date)}
            aria-pressed={selectedDay === day.date}
            aria-label={`${day.weekday} ${day.number}${day.today ? ', today' : ''}`}
            className="flex min-h-14 min-w-0 flex-col items-center justify-center rounded-xl border border-slate-200 bg-slate-50 px-1 text-slate-700 hover:border-teal-600 hover:bg-teal-50 aria-pressed:border-teal-700 aria-pressed:bg-teal-700 aria-pressed:text-white"
          >
            <span className="text-[10px] font-bold uppercase sm:text-xs">{day.weekday.slice(0, 1)}</span>
            <span className="text-sm font-bold">{day.number}</span>
          </button>
        ))}
      </div>
    </Card>
  );
}
