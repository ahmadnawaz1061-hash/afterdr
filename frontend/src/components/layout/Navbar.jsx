import { HeartPulse, LogOut, Menu, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';

export default function Navbar({ mobileOpen, onMobileToggle, collapsed, onCollapse, menuButtonRef }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function signOut() {
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
      <div className="flex h-18 items-center justify-between gap-3 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5 rounded-lg font-bold tracking-tight text-slate-900" aria-label="After Dr home">
          <span className="rounded-xl bg-teal-700 p-2 text-white"><HeartPulse size={24} aria-hidden="true" /></span>
          <span className="text-xl">After <span className="text-teal-700">Dr</span></span>
        </Link>
        <div className="flex items-center gap-4">
          {user ? <span className="hidden max-w-48 truncate text-sm text-slate-600 sm:block">{user.name}</span> : <Link to="/login" className="text-sm font-semibold text-teal-800">Sign in</Link>}
          {user && <button type="button" onClick={signOut} className="icon-button inline-flex" aria-label="Sign out"><LogOut size={19} aria-hidden="true" /></button>}
          <button type="button" className="icon-button inline-flex lg:hidden" onClick={onMobileToggle} ref={menuButtonRef}
            aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileOpen} aria-controls="primary-navigation">
            {mobileOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
          <button type="button" className="icon-button hidden lg:inline-flex" onClick={onCollapse}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed} aria-controls="primary-navigation">
            {collapsed ? <PanelLeftOpen aria-hidden="true" /> : <PanelLeftClose aria-hidden="true" />}
          </button>
        </div>
      </div>
    </header>
  );
}
