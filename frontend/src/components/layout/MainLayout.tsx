import { useState, useCallback } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext';
import { CommandPalette } from '../ui/CommandPalette';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';

function MainLayoutContent() {
  const { collapsed } = useSidebar();
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

  const toggleCommandPalette = useCallback(() => {
    setIsCommandPaletteOpen((prev) => !prev);
  }, []);

  const closeCommandPalette = useCallback(() => {
    setIsCommandPaletteOpen(false);
  }, []);

  useKeyboardShortcuts({ onToggleCommandPalette: toggleCommandPalette });

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900 transition-colors duration-200">
      <Sidebar onOpenCommandPalette={() => setIsCommandPaletteOpen(true)} />
      <div className={`${collapsed ? 'ml-16' : 'ml-64'} transition-all duration-300`}>
        <main className="min-h-screen">
          <Outlet />
        </main>
      </div>
      <CommandPalette isOpen={isCommandPaletteOpen} onClose={closeCommandPalette} />
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
