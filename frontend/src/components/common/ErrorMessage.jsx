import { CircleAlert } from 'lucide-react';

export default function ErrorMessage({
  title = 'Something went wrong',
  message = 'Please try again.',
  error,
  onRetry,
  retryLabel = 'Try again',
}) {
  const detail = error?.response?.data?.detail;
  const backendMessage = typeof detail === 'string'
    ? detail
    : Array.isArray(detail)
      ? detail.map((item) => item?.msg).filter(Boolean).join(' ')
      : null;
  const visibleMessage = backendMessage || message;

  return (
    <div className="state-panel">
      <div role="alert" aria-live="assertive">
        <CircleAlert className="mx-auto mb-4 text-rose-700" size={30} aria-hidden="true" />
        <h3 className="font-semibold text-slate-900">{title}</h3>
        {visibleMessage && <p className="mt-2 text-sm text-slate-600">{visibleMessage}</p>}
      </div>
      {onRetry && <button type="button" onClick={onRetry} className="button-secondary mt-5">{retryLabel}</button>}
    </div>
  );
}
