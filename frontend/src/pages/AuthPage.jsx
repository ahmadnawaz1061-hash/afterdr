import { useState } from 'react';
import { HeartPulse, LogIn, UserPlus } from 'lucide-react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import ErrorMessage from '../components/common/ErrorMessage';
import { useAuth } from '../auth/AuthContext';

export default function AuthPage({ mode }) {
  const registering = mode === 'register';
  const { user, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/dashboard" replace />;

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (registering) await register(form);
      else await login({ email: form.email, password: form.password });
      const destination = location.state?.from;
      navigate(destination?.startsWith('/') ? destination : '/dashboard', { replace: true });
    } catch (requestError) {
      setError(requestError);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-md">
        <Link to="/" className="mx-auto mb-7 flex w-fit items-center gap-2 rounded-lg font-bold text-slate-900">
          <span className="rounded-xl bg-teal-700 p-2 text-white"><HeartPulse size={24} aria-hidden="true" /></span>
          <span className="text-xl">After <span className="text-teal-700">Dr</span></span>
        </Link>
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <h1 className="text-2xl font-bold text-slate-900">{registering ? 'Create your account' : 'Welcome back'}</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {registering ? 'Create a private workspace for your prescriptions and schedules.' : 'Sign in to access your medicine workspace.'}
          </p>
          {error && <div className="mt-5"><ErrorMessage title={registering ? 'Could not create account' : 'Could not sign in'} error={error} message={error.message} /></div>}
          <form className="mt-6 space-y-5" onSubmit={submit}>
            {registering && <label className="block text-sm font-semibold text-slate-700">
              Full name
              <input required minLength={2} maxLength={100} autoComplete="name" value={form.name} onChange={(event) => update('name', event.target.value)} className="mt-2 min-h-12 w-full rounded-xl border border-slate-400 px-4 text-base" />
            </label>}
            <label className="block text-sm font-semibold text-slate-700">
              Email address
              <input required type="email" autoComplete="email" value={form.email} onChange={(event) => update('email', event.target.value)} className="mt-2 min-h-12 w-full rounded-xl border border-slate-400 px-4 text-base" />
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              Password
              <input required type="password" minLength={registering ? 10 : 1} maxLength={128} autoComplete={registering ? 'new-password' : 'current-password'} value={form.password} onChange={(event) => update('password', event.target.value)} className="mt-2 min-h-12 w-full rounded-xl border border-slate-400 px-4 text-base" />
              {registering && <span className="mt-2 block text-xs font-normal text-slate-500">Use at least 10 characters.</span>}
            </label>
            <button disabled={submitting} className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-teal-800 px-5 font-semibold text-white hover:bg-teal-900 disabled:bg-slate-400">
              {registering ? <UserPlus size={18} aria-hidden="true" /> : <LogIn size={18} aria-hidden="true" />}
              {submitting ? 'Please wait…' : registering ? 'Create account' : 'Sign in'}
            </button>
          </form>
          <p className="mt-6 text-center text-sm text-slate-600">
            {registering ? 'Already have an account?' : 'New to After Dr?'}{' '}
            <Link className="font-semibold text-teal-800 underline-offset-4 hover:underline" to={registering ? '/login' : '/register'}>
              {registering ? 'Sign in' : 'Create an account'}
            </Link>
          </p>
        </section>
      </div>
    </main>
  );
}
