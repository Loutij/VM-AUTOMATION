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
      className={`fixed left-0 top-0 h-screen bg-dark-800 border-r border-dark-700 transition-all duration-300 z-40 flex flex-col ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* Logo */}
      <div className="h-16 flex items-center px-4 border-b border-dark-700">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
            <Server size={18} className="text-white" />
          </div>
          {!collapsed && (
            <span className="font-bold text-lg text-white">VM Automation</span>
          )}
        </div>
      </div>

      {/* Navigation principale */}
      <nav className="flex-1 py-4 px-2 overflow-y-auto">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-primary-600 text-white'
                      : 'text-dark-300 hover:bg-dark-700 hover:text-white'
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
      <div className="py-4 px-2 border-t border-dark-700">
        <ul className="space-y-1">
          {bottomNavItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-primary-600 text-white'
                      : 'text-dark-300 hover:bg-dark-700 hover:text-white'
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
        className="absolute -right-3 top-20 w-6 h-6 bg-dark-700 border border-dark-600 rounded-full flex items-center justify-center text-dark-300 hover:text-white hover:bg-dark-600 transition-colors"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>
    </aside>
  );
}
