import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function MainLayout() {
  return (
    <div className="min-h-screen bg-dark-900">
      <Sidebar />
      <div className="ml-64 transition-all duration-300">
        <main className="min-h-screen">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
