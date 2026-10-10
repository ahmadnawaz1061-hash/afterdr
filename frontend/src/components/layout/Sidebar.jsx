import { NavLink } from 'react-router-dom';
import { navigation } from './navigation';

export default function Sidebar({ mobileOpen, collapsed, onNavigate }) {
  return (
    <aside id="primary-navigation" className={`${mobileOpen ? 'block' : 'hidden'} border-b border-slate-200 bg-white lg:sticky lg:top-18 lg:block lg:h-[calc(100dvh-4.5rem)] lg:shrink-0 lg:overflow-y-auto lg:border-r lg:border-b-0 ${collapsed ? 'lg:w-22' : 'lg:w-64'}`}>
      <nav aria-label="Main navigation" className="space-y-1 p-3">
        {navigation.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end onClick={onNavigate} title={collapsed ? label : undefined}
            className={({ isActive }) => `flex min-h-12 items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-colors ${isActive ? 'bg-teal-50 text-teal-800 ring-1 ring-inset ring-teal-200' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
            <Icon size={20} className="shrink-0" aria-hidden="true" />
            <span className={collapsed ? 'lg:sr-only' : ''}>{label}</span>
          </NavLink>
        ))}
      </nav>
      <p className={`m-4 rounded-xl bg-slate-50 p-4 text-xs leading-5 text-slate-600 ${collapsed ? 'lg:hidden' : ''}`}>
        A little support for your next step. Review medicine decisions with your care team.
      </p>
    </aside>
  );
}
