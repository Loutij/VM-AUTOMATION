import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { ThemeProvider } from '../../contexts/ThemeContext';

export function MainLayout() {
  return (
    <ThemeProvider>
      <div className="min-h-screen bg-light-100 dark:bg-dark-900 transition-colors duration-200">
        <Sidebar />
        <div className="ml-64 transition-all duration-300">
          <main className="min-h-screen">
            <Outlet />
          </main>
        </div>
      </div>
    </ThemeProvider>
  );
}
