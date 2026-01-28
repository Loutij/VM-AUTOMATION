import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext';

function MainLayoutContent() {
  const { collapsed } = useSidebar();
  
  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900 transition-colors duration-200">
      <Sidebar />
      <div className={`${collapsed ? 'ml-16' : 'ml-64'} transition-all duration-300`}>
        <main className="min-h-screen">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function MainLayout() {
  return (
    <SidebarProvider>
      <MainLayoutContent />
    </SidebarProvider>
  );
}
