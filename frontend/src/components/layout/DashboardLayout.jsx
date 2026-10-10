import { useEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Navbar from './Navbar';
import Sidebar from './Sidebar';
import { navigation } from './navigation';

export default function DashboardLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const menuButtonRef = useRef(null);
  const mainRef = useRef(null);
  const { pathname } = useLocation();
  const previousPath = useRef(pathname);

  useEffect(() => {
    document.title = `${navigation.find((item) => item.to === pathname)?.label ?? 'Page not found'} | After Dr`;
    // Preserve the natural tab order on arrival. Only move focus after navigation.
    if (previousPath.current !== pathname) {
      previousPath.current = pathname;
      setMobileOpen(false);
      mainRef.current?.focus({ preventScroll: true });
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    }
  }, [pathname]);

  function handleKeyDown(event) {
    if (event.key === 'Escape' && mobileOpen) {
      setMobileOpen(false);
      menuButtonRef.current?.focus();
    }
  }

  return (
    <div className="min-h-dvh" onKeyDown={handleKeyDown}>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <Navbar mobileOpen={mobileOpen} onMobileToggle={() => setMobileOpen((open) => !open)}
        collapsed={collapsed} onCollapse={() => setCollapsed((value) => !value)} menuButtonRef={menuButtonRef} />
      <div className="lg:flex">
        <Sidebar mobileOpen={mobileOpen} collapsed={collapsed} onNavigate={() => {
          setMobileOpen(false);
          mainRef.current?.focus({ preventScroll: true });
        }} />
        <main id="main-content" ref={mainRef} tabIndex={-1} className="min-w-0 flex-1 px-4 py-8 focus-visible:outline-offset-[-2px] sm:px-8 lg:px-10 lg:py-10">
          <div className="mx-auto max-w-6xl"><Outlet /></div>
        </main>
      </div>
    </div>
  );
}
