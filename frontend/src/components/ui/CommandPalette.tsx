import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  Search,
  LayoutDashboard,
  Server,
  Monitor,
  FileCode,
  Rocket,
  Settings,
  HelpCircle,
  Plus,
  ArrowRight,
  Command,
  Package,
} from 'lucide-react';
import type { VirtualMachine, Deployment } from '../../types';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

interface CommandItem {
  id: string;
  label: string;
  category: 'navigation' | 'vms' | 'deployments' | 'actions';
  icon: React.ReactNode;
  action: () => void;
  shortcut?: string;
}

const categoryLabels: Record<string, string> = {
  navigation: 'Navigation',
  actions: 'Actions',
  vms: 'Machines virtuelles',
  deployments: 'Déploiements',
};

const categoryOrder = ['navigation', 'actions', 'vms', 'deployments'];

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Recuperer les donnees en cache de react-query
  const cachedVMs = queryClient.getQueryData<VirtualMachine[]>(['vms']) ?? [];
  const cachedDeployments = queryClient.getQueryData<Deployment[]>(['deployments']) ?? [];

  const navigationItems: CommandItem[] = useMemo(
    () => [
      {
        id: 'nav-dashboard',
        label: 'Dashboard',
        category: 'navigation',
        icon: <LayoutDashboard size={18} />,
        action: () => navigate('/'),
      },
      {
        id: 'nav-vms',
        label: 'Machines virtuelles',
        category: 'navigation',
        icon: <Monitor size={18} />,
        action: () => navigate('/vms'),
      },
      {
        id: 'nav-deployments',
        label: 'Déploiements',
        category: 'navigation',
        icon: <Rocket size={18} />,
        action: () => navigate('/deployments'),
      },
      {
        id: 'nav-hypervisors',
        label: 'Hyperviseurs',
        category: 'navigation',
        icon: <Server size={18} />,
        action: () => navigate('/hypervisors'),
      },
      {
        id: 'nav-templates',
        label: 'Templates',
        category: 'navigation',
        icon: <FileCode size={18} />,
        action: () => navigate('/templates'),
      },
      {
        id: 'nav-marketplace',
        label: 'Marketplace',
        category: 'navigation',
        icon: <Package size={18} />,
        action: () => navigate('/marketplace'),
      },
      {
        id: 'nav-settings',
        label: 'Paramètres',
        category: 'navigation',
        icon: <Settings size={18} />,
        action: () => navigate('/settings'),
        shortcut: 'Ctrl+,',
      },
      {
        id: 'nav-help',
        label: 'Aide',
        category: 'navigation',
        icon: <HelpCircle size={18} />,
        action: () => navigate('/help'),
        shortcut: '?',
      },
    ],
    [navigate]
  );

  const actionItems: CommandItem[] = useMemo(
    () => [
      {
        id: 'action-new-deployment',
        label: 'Nouveau déploiement',
        category: 'actions',
        icon: <Plus size={18} />,
        action: () => navigate('/deployments/new'),
        shortcut: 'Ctrl+N',
      },
      {
        id: 'action-add-hypervisor',
        label: 'Ajouter un hyperviseur',
        category: 'actions',
        icon: <Plus size={18} />,
        action: () => navigate('/hypervisors'),
      },
    ],
    [navigate]
  );

  const vmItems: CommandItem[] = useMemo(
    () =>
      cachedVMs.map((vm) => ({
        id: `vm-${vm.id}`,
        label: vm.name,
        category: 'vms' as const,
        icon: <Monitor size={18} />,
        action: () => navigate('/vms'),
      })),
    [cachedVMs, navigate]
  );

  const deploymentItems: CommandItem[] = useMemo(
    () =>
      cachedDeployments.map((dep) => ({
        id: `dep-${dep.id}`,
        label: dep.name || dep.vm_name,
        category: 'deployments' as const,
        icon: <Rocket size={18} />,
        action: () => navigate('/deployments'),
      })),
    [cachedDeployments, navigate]
  );

  const allItems = useMemo(
    () => [...navigationItems, ...actionItems, ...vmItems, ...deploymentItems],
    [navigationItems, actionItems, vmItems, deploymentItems]
  );

  const filteredItems = useMemo(() => {
    if (!query.trim()) {
      // Sans recherche, afficher navigation + actions uniquement
      return [...navigationItems, ...actionItems];
    }
    const lowerQuery = query.toLowerCase();
    return allItems.filter((item) => item.label.toLowerCase().includes(lowerQuery));
  }, [query, allItems, navigationItems, actionItems]);

  // Grouper par categorie dans l'ordre defini
  const groupedItems = useMemo(() => {
    const groups: Record<string, CommandItem[]> = {};
    for (const item of filteredItems) {
      if (!groups[item.category]) {
        groups[item.category] = [];
      }
      groups[item.category].push(item);
    }
    return categoryOrder
      .filter((cat) => groups[cat]?.length)
      .map((cat) => ({ category: cat, items: groups[cat] }));
  }, [filteredItems]);

  // Liste a plat pour la navigation clavier
  const flatItems = useMemo(
    () => groupedItems.flatMap((g) => g.items),
    [groupedItems]
  );

  // Reset a l'ouverture
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      // Focus l'input au prochain tick
      setTimeout(() => inputRef.current?.focus(), 0);
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  // Reset de l'index quand les resultats changent
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Scroll vers l'element selectionne
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${selectedIndex}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  const executeItem = useCallback(
    (item: CommandItem) => {
      onClose();
      // Execute apres la fermeture pour eviter les conflits
      setTimeout(() => item.action(), 0);
    },
    [onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) => (prev + 1) % flatItems.length);
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => (prev - 1 + flatItems.length) % flatItems.length);
          break;
        case 'Enter':
          e.preventDefault();
          if (flatItems[selectedIndex]) {
            executeItem(flatItems[selectedIndex]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    },
    [flatItems, selectedIndex, executeItem, onClose]
  );

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) {
      onClose();
    }
  };

  if (!isOpen) return null;

  let flatIndex = 0;

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-[70] flex items-start justify-center pt-[15vh] p-4 bg-black/50 dark:bg-black/60 backdrop-blur-sm animate-in fade-in duration-150"
    >
      <div
        className="w-full max-w-lg bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-700 rounded-xl shadow-2xl animate-in zoom-in-95 duration-150 overflow-hidden"
        onKeyDown={handleKeyDown}
      >
        {/* Barre de recherche */}
        <div className="flex items-center gap-3 px-4 border-b border-light-200 dark:border-dark-700">
          <Search size={20} className="text-gray-400 dark:text-dark-400 flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher une page, VM, déploiement..."
            className="flex-1 py-3.5 bg-transparent text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-400 outline-none text-sm"
          />
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 bg-light-100 dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded text-[10px] text-gray-500 dark:text-dark-400 font-mono">
            ESC
          </kbd>
        </div>

        {/* Resultats */}
        <div ref={listRef} className="max-h-80 overflow-y-auto py-2">
          {groupedItems.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-500 dark:text-dark-400 text-sm">
              Aucun resultat pour &laquo; {query} &raquo;
            </div>
          ) : (
            groupedItems.map((group) => (
              <div key={group.category}>
                <div className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-dark-500">
                  {categoryLabels[group.category]}
                </div>
                {group.items.map((item) => {
                  const currentIndex = flatIndex++;
                  const isSelected = currentIndex === selectedIndex;
                  return (
                    <button
                      key={item.id}
                      data-index={currentIndex}
                      onClick={() => executeItem(item)}
                      onMouseEnter={() => setSelectedIndex(currentIndex)}
                      className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                        isSelected
                          ? 'bg-oto-50 dark:bg-oto-600/20 text-oto-700 dark:text-oto-400'
                          : 'text-gray-700 dark:text-dark-300 hover:bg-light-100 dark:hover:bg-dark-700/50'
                      }`}
                    >
                      <span
                        className={`flex-shrink-0 ${
                          isSelected
                            ? 'text-oto-500 dark:text-oto-400'
                            : 'text-gray-400 dark:text-dark-400'
                        }`}
                      >
                        {item.icon}
                      </span>
                      <span className="flex-1 text-sm font-medium truncate">{item.label}</span>
                      {item.shortcut && (
                        <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 bg-light-100 dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded text-[10px] text-gray-500 dark:text-dark-400 font-mono">
                          {item.shortcut}
                        </kbd>
                      )}
                      {isSelected && (
                        <ArrowRight
                          size={14}
                          className="text-oto-400 dark:text-oto-500 flex-shrink-0"
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-light-200 dark:border-dark-700 bg-light-50 dark:bg-dark-800/50 text-[11px] text-gray-400 dark:text-dark-500">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-light-100 dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded font-mono">
                &uarr;
              </kbd>
              <kbd className="px-1 py-0.5 bg-light-100 dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded font-mono">
                &darr;
              </kbd>
              naviguer
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-light-100 dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded font-mono">
                &crarr;
              </kbd>
              ouvrir
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Command size={11} />
            <span>K pour ouvrir</span>
          </div>
        </div>
      </div>
    </div>
  );
}
