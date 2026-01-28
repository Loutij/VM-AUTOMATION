import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Server,
  Monitor,
  FileCode,
  Rocket,
  Package,
  Settings,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useState } from 'react';

// Composant Logo OTO
function OTOLogo({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex items-center gap-3">
      {/* Logo icône */}
      <div className="w-9 h-9 border-2 border-gray-900 dark:border-white rounded-xl flex items-center justify-center">
        <span className="font-black text-sm text-gray-900 dark:text-white">OTO</span>
      </div>
      {!collapsed && (
        <div className="flex flex-col">
          <span className="font-black text-base uppercase tracking-tight text-gray-900 dark:text-white leading-none">
            VM Automation
          </span>
          <span className="text-[10px] text-gray-500 dark:text-dark-400 uppercase tracking-widest">
            OTO Technology
          </span>
        </div>
      )}
    </div>
  );
}

interface NavItem {
  to: string;
  icon: React.ReactNode;
  label: string;
}

const navItems: NavItem[] = [
  { to: '/', icon: <LayoutDashboard size={20} />, label: 'Dashboard' },
  { to: '/hypervisors', icon: <Server size={20} />, label: 'Hyperviseurs' },
  { to: '/vms', icon: <Monitor size={20} />, label: 'Machines Virtuelles' },
  { to: '/templates', icon: <FileCode size={20} />, label: 'Templates' },
  { to: '/deployments', icon: <Rocket size={20} />, label: 'Déploiements' },
  { to: '/marketplace', icon: <Package size={20} />, label: 'Marketplace' },
];

const bottomNavItems: NavItem[] = [
  { to: '/settings', icon: <Settings size={20} />, label: 'Paramètres' },
  { to: '/help', icon: <HelpCircle size={20} />, label: 'Aide' },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`fixed left-0 top-0 h-screen bg-white dark:bg-dark-800 border-r border-light-300 dark:border-dark-700 transition-all duration-300 z-40 flex flex-col ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* Logo OTO */}
      <div className="h-16 flex items-center px-4 border-b border-light-200 dark:border-dark-700">
        <OTOLogo collapsed={collapsed} />
      </div>

      {/* Navigation principale */}
      <nav className="flex-1 py-4 px-2 overflow-y-auto">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                    isActive
                      ? 'bg-oto-500 text-white shadow-sm'
                      : 'text-gray-600 dark:text-dark-300 hover:bg-light-100 dark:hover:bg-dark-700 hover:text-gray-900 dark:hover:text-white'
                  }`
                }
              >
                {item.icon}
                {!collapsed && <span className="font-medium">{item.label}</span>}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Navigation secondaire */}
      <div className="py-4 px-2 border-t border-light-200 dark:border-dark-700">
        <ul className="space-y-1">
          {bottomNavItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                    isActive
                      ? 'bg-oto-500 text-white shadow-sm'
                      : 'text-gray-600 dark:text-dark-300 hover:bg-light-100 dark:hover:bg-dark-700 hover:text-gray-900 dark:hover:text-white'
                  }`
                }
              >
                {item.icon}
                {!collapsed && <span className="font-medium">{item.label}</span>}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>

      {/* Toggle collapse */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 w-6 h-6 bg-white dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-full flex items-center justify-center text-gray-500 dark:text-dark-300 hover:text-gray-900 dark:hover:text-white hover:bg-light-100 dark:hover:bg-dark-600 transition-colors shadow-sm"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>
    </aside>
  );
}
