import { CalendarClock, FileHeart, FilePenLine, House, LayoutDashboard, Pill, ShieldCheck } from 'lucide-react';

export const navigation = [
  { to: '/', label: 'Welcome', icon: House },
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/prescription', label: 'Prescription reader', icon: FileHeart },
  { to: '/scheduler', label: 'Medicine scheduler', icon: CalendarClock },
  { to: '/alternatives', label: 'Medicine alternatives', icon: Pill },
  { to: '/verification', label: 'Medicine Packaging Check', icon: ShieldCheck },
  { to: '/reporting', label: 'Draft reporting', icon: FilePenLine },
];
