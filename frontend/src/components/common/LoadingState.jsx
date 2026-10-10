import { LoaderCircle } from 'lucide-react';

export default function LoadingState({ title = 'Loading…', message = 'Please wait while we prepare your content.' }) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <LoaderCircle className="mx-auto mb-4 text-teal-700 motion-safe:animate-spin" size={30} aria-hidden="true" />
      <h3 className="font-semibold text-slate-900">{title}</h3>
      {message && <p className="mt-2 text-sm text-slate-600">{message}</p>}
    </div>
  );
}
