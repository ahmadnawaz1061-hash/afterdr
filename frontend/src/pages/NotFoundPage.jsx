import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return <div className="state-panel">
    <p className="text-sm font-semibold text-teal-700">404</p>
    <h1 className="mt-3 text-3xl font-bold text-slate-900">Page not found</h1>
    <p className="mt-3 text-slate-600">Choose a tool from the navigation or return to your dashboard.</p>
    <Link to="/dashboard" className="button-secondary mt-6">Go to dashboard</Link>
  </div>;
}
