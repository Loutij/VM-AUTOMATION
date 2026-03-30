import { useState, useEffect, useMemo, type ReactNode } from 'react';
import {
  Search,
  LayoutGrid,
  List,
  Star,
  Clock,
  Download,
  Check,
  X,
  Info,
  Package,
  ArrowUpDown,
  Filter,
  Sparkles,
  Monitor,
  ExternalLink,
  Layers,
  Zap,
  Shield,
  Globe,
  Database,
  Code,
  Activity,
  Wrench,
  HardDrive,
  Network,
  FolderArchive,
  ChevronRight,
  ChevronDown,
  TrendingUp,
  Box,
  Terminal,
  Copy,
  CheckCheck,
} from 'lucide-react';
import { softwareApi } from '../services/api';
import type { SoftwarePackage, SoftwareCategory_Info, SoftwareProfile } from '../types';
import { Header } from '../components/layout';
import { Button, Modal, Skeleton, EmptyState } from '../components/ui';

// Lucide icons for categories (replaces emojis for a cleaner look)
const CATEGORY_LUCIDE: Record<string, typeof Monitor> = {
  windows_role: Monitor,
  remote_access: Shield,
  database: Database,
  webserver: Globe,
  development: Code,
  runtime: Zap,
  monitoring: Activity,
  security: Shield,
  utilities: Wrench,
  browser: Globe,
  containers: Box,
  file_transfer: FolderArchive,
  network: Network,
  backup: HardDrive,
  other: Package,
};

// Gradient accents per category
const CATEGORY_GRADIENT: Record<string, string> = {
  windows_role: 'from-blue-500/20 to-blue-600/5',
  remote_access: 'from-purple-500/20 to-purple-600/5',
  database: 'from-amber-500/20 to-amber-600/5',
  webserver: 'from-green-500/20 to-green-600/5',
  development: 'from-cyan-500/20 to-cyan-600/5',
  runtime: 'from-yellow-500/20 to-yellow-600/5',
  monitoring: 'from-orange-500/20 to-orange-600/5',
  security: 'from-red-500/20 to-red-600/5',
  utilities: 'from-slate-500/20 to-slate-600/5',
  browser: 'from-indigo-500/20 to-indigo-600/5',
  containers: 'from-teal-500/20 to-teal-600/5',
  file_transfer: 'from-pink-500/20 to-pink-600/5',
  network: 'from-violet-500/20 to-violet-600/5',
  backup: 'from-emerald-500/20 to-emerald-600/5',
  other: 'from-gray-500/20 to-gray-600/5',
};

const CATEGORY_ACCENT: Record<string, string> = {
  windows_role: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  remote_access: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  database: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  webserver: 'text-green-400 bg-green-500/10 border-green-500/20',
  development: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  runtime: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
  monitoring: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
  security: 'text-red-400 bg-red-500/10 border-red-500/20',
  utilities: 'text-slate-400 bg-slate-500/10 border-slate-500/20',
  browser: 'text-indigo-400 bg-indigo-500/10 border-indigo-500/20',
  containers: 'text-teal-400 bg-teal-500/10 border-teal-500/20',
  file_transfer: 'text-pink-400 bg-pink-500/10 border-pink-500/20',
  network: 'text-violet-400 bg-violet-500/10 border-violet-500/20',
  backup: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  other: 'text-gray-400 bg-gray-500/10 border-gray-500/20',
};

// Icon glow/shadow color per category (used in details modal)
const CATEGORY_GLOW: Record<string, string> = {
  windows_role: 'shadow-blue-500/40',
  remote_access: 'shadow-purple-500/40',
  database: 'shadow-amber-500/40',
  webserver: 'shadow-green-500/40',
  development: 'shadow-cyan-500/40',
  runtime: 'shadow-yellow-500/40',
  monitoring: 'shadow-orange-500/40',
  security: 'shadow-red-500/40',
  utilities: 'shadow-slate-500/40',
  browser: 'shadow-indigo-500/40',
  containers: 'shadow-teal-500/40',
  file_transfer: 'shadow-pink-500/40',
  network: 'shadow-violet-500/40',
  backup: 'shadow-emerald-500/40',
  other: 'shadow-gray-500/40',
};

// Left-border accent color per category (for selected state in list)
const CATEGORY_BORDER: Record<string, string> = {
  windows_role: 'border-l-blue-500',
  remote_access: 'border-l-purple-500',
  database: 'border-l-amber-500',
  webserver: 'border-l-green-500',
  development: 'border-l-cyan-500',
  runtime: 'border-l-yellow-500',
  monitoring: 'border-l-orange-500',
  security: 'border-l-red-500',
  utilities: 'border-l-slate-500',
  browser: 'border-l-indigo-500',
  containers: 'border-l-teal-500',
  file_transfer: 'border-l-pink-500',
  network: 'border-l-violet-500',
  backup: 'border-l-emerald-500',
  other: 'border-l-gray-500',
};

// Dot color per category for section headers
const CATEGORY_DOT: Record<string, string> = {
  windows_role: 'bg-blue-400',
  remote_access: 'bg-purple-400',
  database: 'bg-amber-400',
  webserver: 'bg-green-400',
  development: 'bg-cyan-400',
  runtime: 'bg-yellow-400',
  monitoring: 'bg-orange-400',
  security: 'bg-red-400',
  utilities: 'bg-slate-400',
  browser: 'bg-indigo-400',
  containers: 'bg-teal-400',
  file_transfer: 'bg-pink-400',
  network: 'bg-violet-400',
  backup: 'bg-emerald-400',
  other: 'bg-gray-400',
};

type SortOption = 'name' | 'popular' | 'time' | 'recent';
type OsFilter = 'all' | 'windows' | 'linux';

interface MarketplaceProps {
  selectionMode?: boolean;
  selectedPackages?: string[];
  onSelectionChange?: (packages: string[]) => void;
}

export function Marketplace({
  selectionMode = false,
  selectedPackages = [],
  onSelectionChange,
}: MarketplaceProps) {
  const [software, setSoftware] = useState<SoftwarePackage[]>([]);
  const [categories, setCategories] = useState<SoftwareCategory_Info[]>([]);
  const [profiles, setProfiles] = useState<SoftwareProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [detailsModal, setDetailsModal] = useState<SoftwarePackage | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set(selectedPackages));
  const [sortBy, setSortBy] = useState<SortOption>('name');
  const [osFilter, setOsFilter] = useState<OsFilter>('all');
  const [showProfiles, setShowProfiles] = useState(false);

  // Debounce search (300ms)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Load data
  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        setLoading(true);
        const [softwareData, categoriesData, profilesData] = await Promise.all([
          softwareApi.list({ page_size: 200 }),
          softwareApi.getCategories(),
          softwareApi.getProfiles(),
        ]);
        if (!cancelled) {
          setSoftware(softwareData.items);
          setCategories(categoriesData);
          setProfiles(profilesData.profiles);
        }
      } catch (error) {
        if (!cancelled) {
          console.error('Error loading marketplace:', error);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    fetchData();
    return () => { cancelled = true; };
  }, []);

  // Filter and sort software
  const filteredSoftware = useMemo(() => {
    let result = software.filter((pkg) => {
      if (selectedCategory !== 'all' && pkg.category !== selectedCategory) return false;
      if (osFilter !== 'all' && pkg.os_family && pkg.os_family !== osFilter) return false;
      if (debouncedSearch) {
        const query = debouncedSearch.toLowerCase();
        return (
          pkg.name.toLowerCase().includes(query) ||
          pkg.display_name.toLowerCase().includes(query) ||
          pkg.description?.toLowerCase().includes(query) ||
          pkg.tags.some((tag) => tag.toLowerCase().includes(query))
        );
      }
      return true;
    });

    // Sort
    switch (sortBy) {
      case 'name':
        result = [...result].sort((a, b) => a.display_name.localeCompare(b.display_name));
        break;
      case 'popular':
        result = [...result].sort((a, b) => b.install_count - a.install_count);
        break;
      case 'time':
        result = [...result].sort((a, b) => a.install_time_minutes - b.install_time_minutes);
        break;
      case 'recent':
        result = [...result].sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        break;
    }

    return result;
  }, [software, selectedCategory, debouncedSearch, sortBy, osFilter]);

  // Featured software
  const featuredSoftware = useMemo(
    () => software.filter((pkg) => pkg.is_featured),
    [software]
  );

  // Selection handlers
  const toggleSelection = (name: string) => {
    const newSelected = new Set(selected);
    if (newSelected.has(name)) {
      newSelected.delete(name);
    } else {
      newSelected.add(name);
    }
    setSelected(newSelected);
    onSelectionChange?.(Array.from(newSelected));
  };

  const selectProfile = (profile: SoftwareProfile) => {
    const newSelected = new Set(profile.packages);
    setSelected(newSelected);
    onSelectionChange?.(profile.packages);
    setShowProfiles(false);
  };

  const clearSelection = () => {
    setSelected(new Set());
    onSelectionChange?.([]);
  };

  const handleSeedCatalog = async () => {
    try {
      const result = await softwareApi.seedCatalog();
      alert(`Catalogue initialisé: ${result.created} créés, ${result.skipped} ignorés`);
      const softwareData = await softwareApi.list({ page_size: 200 });
      setSoftware(softwareData.items);
    } catch (error) {
      console.error('Error seeding catalog:', error);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-light-100 dark:bg-dark-900">
        <Header title={selectionMode ? 'Sélection logiciels' : 'Marketplace'} />
        <div className="p-4 sm:p-6 space-y-6">
          <div className="flex gap-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-10 w-28 rounded-full" />
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[...Array(8)].map((_, i) => (
              <Skeleton key={i} className="h-56 rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (software.length === 0) {
    return (
      <div className="min-h-screen bg-light-100 dark:bg-dark-900">
        <Header title="Marketplace" />
        <div className="flex flex-col items-center justify-center min-h-[60vh]">
          <EmptyState
            icon={Package}
            title="Catalogue vide"
            description="Le catalogue logiciel n'a pas encore été initialisé. Cliquez ci-dessous pour charger les logiciels disponibles."
            action={{
              label: 'Initialiser le catalogue',
              onClick: handleSeedCatalog,
              icon: Download,
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title={selectionMode ? 'Sélection logiciels' : 'Marketplace'} />
      <div className="p-4 sm:p-6 space-y-5">

      {/* Stats bar + Search */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        {/* Search */}
        <div className="relative w-full sm:max-w-md">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-400" />
          <input
            type="text"
            placeholder="Rechercher un logiciel, une catégorie ou un tag..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-10 py-2.5 bg-white dark:bg-dark-800 border border-light-300 dark:border-dark-600 rounded-lg text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-oto-500 focus:border-transparent transition-all text-sm"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-light-200 dark:hover:bg-dark-700 text-gray-400 hover:text-gray-600 dark:hover:text-dark-200 transition-colors"
            >
              <X size={15} />
            </button>
          )}
        </div>

        {/* Stats pills */}
        <div className="flex items-center gap-3 flex-shrink-0">
          {[
            { value: software.length,   label: 'Logiciels',  icon: Package  },
            { value: categories.length, label: 'Catégories', icon: Layers   },
            { value: profiles.length,   label: 'Profils',    icon: Sparkles },
          ].map(({ value, label, icon: Icon }, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-700"
            >
              <Icon size={14} className="text-gray-400 dark:text-dark-400" />
              <span className="text-sm font-bold text-gray-900 dark:text-white tabular-nums">{value}</span>
              <span className="text-xs text-gray-500 dark:text-dark-400">{label}</span>
            </div>
          ))}
        </div>
      </div>
      {/* Selection bar */}
      {selected.size > 0 && (
        <div className="flex items-center justify-between px-4 py-3 bg-oto-500/10 dark:bg-oto-500/10 border border-oto-500/20 rounded-xl animate-in slide-in-from-top duration-200">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-oto-500 flex items-center justify-center text-white font-bold text-sm">
              {selected.size}
            </div>
            <span className="text-sm font-medium text-oto-600 dark:text-oto-400">
              logiciel{selected.size > 1 ? 's' : ''} sélectionné{selected.size > 1 ? 's' : ''}
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={clearSelection}>
            <X size={14} className="mr-1" />
            Tout désélectionner
          </Button>
        </div>
      )}

      {/* Featured section */}
      {!selectionMode && featuredSoftware.length > 0 && !debouncedSearch && selectedCategory === 'all' && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <div className="relative flex items-center justify-center w-7 h-7">
              <div className="absolute inset-0 rounded-full bg-yellow-400/20 animate-pulse" />
              <Star size={16} className="relative text-yellow-400 fill-yellow-400 drop-shadow-[0_0_4px_rgba(250,204,21,0.7)]" />
            </div>
            <div className="relative">
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Recommandés</h2>
              <div className="absolute -bottom-0.5 left-0 right-0 h-0.5 rounded-full bg-gradient-to-r from-yellow-400/80 via-yellow-300/60 to-transparent" />
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {featuredSoftware.slice(0, 5).map((pkg) => {
              const IconComponent = CATEGORY_LUCIDE[pkg.category] || Package;
              return (
                <button
                  key={pkg.id}
                  onClick={() => setDetailsModal(pkg)}
                  className="group relative overflow-hidden p-4 rounded-xl bg-white/80 dark:bg-dark-800/80 backdrop-blur-sm border border-light-200 dark:border-dark-700 hover:border-yellow-500/60 dark:hover:border-yellow-500/40 transition-all duration-200 hover:shadow-lg hover:shadow-yellow-500/10 dark:hover:shadow-yellow-500/5 hover:-translate-y-0.5"
                >
                  {/* Shimmer effect on hover */}
                  <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none overflow-hidden rounded-xl">
                    <div className="absolute -inset-full top-0 h-full w-1/2 z-10 block transform -skew-x-12 bg-gradient-to-r from-transparent to-white/10 dark:to-white/5 group-hover:animate-[shimmer_0.7s_ease-in-out]" />
                  </div>
                  <div className={`absolute inset-0 bg-gradient-to-br ${CATEGORY_GRADIENT[pkg.category] || CATEGORY_GRADIENT.other} opacity-0 group-hover:opacity-100 transition-opacity duration-200`} />
                  <div className="relative">
                    <div className="flex items-center gap-3 mb-2">
                      <div className={`w-10 h-10 rounded-lg border flex items-center justify-center ${CATEGORY_ACCENT[pkg.category] || CATEGORY_ACCENT.other} group-hover:scale-105 transition-transform duration-200`}>
                        <IconComponent size={20} />
                      </div>
                      <div className="flex-1 min-w-0 text-left">
                        <h3 className="font-semibold text-sm text-gray-900 dark:text-white truncate">{pkg.display_name}</h3>
                        {pkg.version && (
                          <span className="text-xs text-gray-500 dark:text-dark-400">v{pkg.version}</span>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-dark-400 line-clamp-2 text-left">
                      {pkg.short_description || pkg.description || 'Pas de description'}
                    </p>
                  </div>
                  {/* Star badge with glow */}
                  <div className="absolute top-2 right-2 flex items-center justify-center w-5 h-5 rounded-full bg-yellow-400/15 dark:bg-yellow-400/10 group-hover:bg-yellow-400/25 transition-colors duration-200">
                    <Star size={11} className="text-yellow-400 fill-yellow-400 drop-shadow-[0_0_3px_rgba(250,204,21,0.6)]" />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Profiles section */}
      {profiles.length > 0 && (
        <div>
          <button
            onClick={() => setShowProfiles(!showProfiles)}
            className="flex items-center gap-2 mb-4 group"
          >
            <div className="w-7 h-7 flex items-center justify-center rounded-lg bg-oto-500/10 dark:bg-oto-500/15 group-hover:bg-oto-500/20 transition-colors duration-200">
              <Layers size={16} className="text-oto-500 group-hover:scale-110 transition-transform duration-200" />
            </div>
            <div className="relative">
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Profils pré-configurés</h2>
              <div className="absolute -bottom-0.5 left-0 right-0 h-0.5 rounded-full bg-gradient-to-r from-oto-500/70 via-oto-400/40 to-transparent" />
            </div>
            <ChevronRight
              size={18}
              className={`text-gray-400 group-hover:text-oto-500 transition-all duration-200 ${showProfiles ? 'rotate-90' : ''}`}
            />
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-oto-500/10 text-oto-600 dark:bg-oto-500/20 dark:text-oto-400 border border-oto-500/20 ml-1">
              {profiles.length} profils
            </span>
          </button>
          <div
            className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 transition-all duration-300 origin-top ${
              showProfiles
                ? 'opacity-100 scale-y-100 max-h-[2000px]'
                : 'opacity-0 scale-y-95 max-h-0 overflow-hidden pointer-events-none'
            }`}
          >
            {profiles.map((profile) => (
              <button
                key={profile.name}
                onClick={() => selectProfile(profile)}
                className="group flex items-start gap-3 p-4 rounded-xl bg-white/80 dark:bg-dark-800/80 backdrop-blur-sm border border-light-200 dark:border-dark-700 hover:border-oto-500/50 dark:hover:border-oto-500/40 transition-all duration-200 hover:shadow-md hover:shadow-oto-500/5 hover:-translate-y-0.5 text-left"
              >
                <div className="w-10 h-10 rounded-lg bg-oto-500/10 border border-oto-500/20 flex items-center justify-center text-oto-500 flex-shrink-0 group-hover:bg-oto-500 group-hover:text-white group-hover:border-oto-500 group-hover:scale-105 transition-all duration-200">
                  <Layers size={20} />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-sm text-gray-900 dark:text-white group-hover:text-oto-500 dark:group-hover:text-oto-400 transition-colors duration-200">
                    {profile.display_name}
                  </h3>
                  <p className="text-xs text-gray-500 dark:text-dark-400 line-clamp-2 mt-0.5">
                    {profile.description}
                  </p>
                  <div className="flex items-center gap-1.5 mt-2">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-dark-700 text-gray-500 dark:text-dark-400 border border-gray-200 dark:border-dark-600 group-hover:bg-oto-500/10 group-hover:text-oto-600 dark:group-hover:bg-oto-500/15 dark:group-hover:text-oto-400 group-hover:border-oto-500/20 transition-colors duration-200">
                      <Package size={10} />
                      {profile.package_count} packages
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Filters toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        {/* OS filter */}
        <div className="flex rounded-lg border border-light-200 dark:border-dark-600 overflow-hidden bg-white dark:bg-dark-800 shadow-sm">
          {(
            [
              { key: 'all' as OsFilter, label: 'Tous', Icon: null },
              { key: 'windows' as OsFilter, label: 'Windows', Icon: Monitor },
              { key: 'linux' as OsFilter, label: 'Linux', Icon: Terminal },
            ] as { key: OsFilter; label: string; Icon: React.ElementType | null }[]
          ).map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setOsFilter(key)}
              title={label}
              className={`px-3 py-2 text-sm font-medium transition-all duration-150 flex items-center gap-1.5 ${
                osFilter === key
                  ? 'bg-oto-500 text-white scale-[0.97]'
                  : 'text-gray-600 dark:text-dark-300 hover:bg-light-100 dark:hover:bg-dark-700'
              }`}
            >
              {Icon && (
                <Icon
                  size={13}
                  className={osFilter === key ? 'text-white/90' : 'text-gray-400 dark:text-dark-500'}
                />
              )}
              {label}
            </button>
          ))}
        </div>

        {/* Sort */}
        <div className="flex items-center gap-1.5 text-sm">
          <ArrowUpDown size={14} className="text-gray-400 dark:text-dark-500 shrink-0" />
          <div className="relative">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="appearance-none bg-white dark:bg-dark-800 border border-light-200 dark:border-dark-600 rounded-lg pl-3 pr-8 py-2 text-gray-700 dark:text-dark-200 text-sm focus:outline-none focus:ring-2 focus:ring-oto-500/30 hover:border-oto-500/40 dark:hover:border-oto-500/40 transition-colors cursor-pointer shadow-sm"
            >
              <option value="name">Nom A-Z</option>
              <option value="popular">Popularité</option>
              <option value="time">Temps d'install</option>
              <option value="recent">Plus récents</option>
            </select>
            <ChevronDown
              size={13}
              className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-500"
            />
          </div>
        </div>

        <div className="flex-1" />

        {/* View toggle */}
        <div className="flex items-center gap-2.5">
          {/* Result count badge */}
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-light-100 dark:bg-dark-700 border border-light-200 dark:border-dark-600 text-xs font-medium text-gray-600 dark:text-dark-300 select-none">
            <span className="font-bold text-oto-500">{filteredSoftware.length}</span>
            résultat{filteredSoftware.length !== 1 ? 's' : ''}
          </span>
          {/* Grid / List toggle */}
          <div className="flex rounded-lg border border-light-200 dark:border-dark-600 overflow-hidden shadow-sm">
            <button
              onClick={() => setViewMode('grid')}
              title="Vue grille"
              className={`p-2 transition-all duration-150 ${
                viewMode === 'grid'
                  ? 'bg-oto-500 text-white scale-[0.94]'
                  : 'bg-white dark:bg-dark-800 text-gray-500 dark:text-dark-400 hover:bg-light-100 dark:hover:bg-dark-700'
              }`}
            >
              <LayoutGrid size={16} />
            </button>
            <button
              onClick={() => setViewMode('list')}
              title="Vue liste"
              className={`p-2 transition-all duration-150 ${
                viewMode === 'list'
                  ? 'bg-oto-500 text-white scale-[0.94]'
                  : 'bg-white dark:bg-dark-800 text-gray-500 dark:text-dark-400 hover:bg-light-100 dark:hover:bg-dark-700'
              }`}
            >
              <List size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Category pills */}
      <div className="relative">
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-dark-600">
          {/* "Tous" pill */}
          <button
            onClick={() => setSelectedCategory('all')}
            className={`px-4 py-2 rounded-full whitespace-nowrap text-sm font-medium transition-all duration-150 flex items-center gap-1.5 ${
              selectedCategory === 'all'
                ? 'bg-oto-500 text-white shadow-md shadow-oto-500/25 scale-105'
                : 'bg-white dark:bg-dark-800 text-gray-600 dark:text-dark-300 border border-light-200 dark:border-dark-600 hover:border-oto-500/50 dark:hover:border-oto-500/50 hover:scale-[1.02]'
            }`}
          >
            <Filter size={14} />
            Tous
            <span
              className={`inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full text-[10px] font-bold ${
                selectedCategory === 'all'
                  ? 'bg-white/20 text-white'
                  : 'bg-light-200 dark:bg-dark-600 text-gray-500 dark:text-dark-400'
              }`}
            >
              {software.length}
            </span>
          </button>
          {categories.map((cat) => {
            const IconComp = CATEGORY_LUCIDE[cat.id] || Package;
            const isActive = selectedCategory === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`px-4 py-2 rounded-full whitespace-nowrap text-sm font-medium transition-all duration-150 flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-oto-500 text-white shadow-md shadow-oto-500/25 scale-105'
                    : 'bg-white dark:bg-dark-800 text-gray-600 dark:text-dark-300 border border-l-2 border-light-200 dark:border-dark-600 border-l-oto-400/40 hover:border-oto-500/50 dark:hover:border-oto-500/50 hover:scale-[1.02]'
                }`}
              >
                <IconComp size={14} />
                {cat.name}
                <span
                  className={`inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full text-[10px] font-bold ${
                    isActive
                      ? 'bg-white/20 text-white'
                      : 'bg-light-200 dark:bg-dark-600 text-gray-500 dark:text-dark-400'
                  }`}
                >
                  {cat.count}
                </span>
              </button>
            );
          })}
        </div>
        {/* Scroll fade indicator on right edge */}
        <div className="pointer-events-none absolute right-0 top-0 bottom-1 w-12 bg-gradient-to-l from-light-50 dark:from-dark-900 to-transparent rounded-r-lg" />
      </div>

      {/* Software list */}
      {filteredSoftware.length === 0 ? (
        <EmptyState
          icon={Search}
          title="Aucun logiciel trouvé"
          description={
            debouncedSearch
              ? `Aucun résultat pour "${debouncedSearch}". Essayez un autre terme de recherche.`
              : 'Aucun logiciel ne correspond aux filtres sélectionnés.'
          }
          action={{
            label: 'Réinitialiser les filtres',
            onClick: () => {
              setSearchQuery('');
              setSelectedCategory('all');
              setOsFilter('all');
            },
          }}
        />
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredSoftware.map((pkg) => (
            <SoftwareCard
              key={pkg.id}
              software={pkg}
              isSelected={selected.has(pkg.name)}
              onToggle={() => toggleSelection(pkg.name)}
              onDetails={() => setDetailsModal(pkg)}
              selectionMode={selectionMode}
            />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredSoftware.map((pkg) => (
            <SoftwareListItem
              key={pkg.id}
              software={pkg}
              isSelected={selected.has(pkg.name)}
              onToggle={() => toggleSelection(pkg.name)}
              onDetails={() => setDetailsModal(pkg)}
              selectionMode={selectionMode}
            />
          ))}
        </div>
      )}

      {/* Details modal */}
      {detailsModal && (
        <SoftwareDetailsModal
          software={detailsModal}
          isOpen={!!detailsModal}
          onClose={() => setDetailsModal(null)}
          isSelected={selected.has(detailsModal.name)}
          onToggle={() => toggleSelection(detailsModal.name)}
        />
      )}
      </div>
    </div>
  );
}

// Software card component
interface SoftwareCardProps {
  software: SoftwarePackage;
  isSelected: boolean;
  onToggle: () => void;
  onDetails: () => void;
  selectionMode: boolean;
}

function SoftwareCard({ software, isSelected, onToggle, onDetails, selectionMode }: SoftwareCardProps) {
  const IconComponent = CATEGORY_LUCIDE[software.category] || Package;
  const accentClass = CATEGORY_ACCENT[software.category] || CATEGORY_ACCENT.other;
  const gradientClass = CATEGORY_GRADIENT[software.category] || CATEGORY_GRADIENT.other;

  return (
    <div
      className={`group relative overflow-hidden bg-white dark:bg-dark-800 rounded-xl border transition-all duration-300 hover:shadow-xl hover:-translate-y-1 ${
        isSelected
          ? 'border-oto-500 ring-2 ring-oto-500/25 shadow-lg shadow-oto-500/15'
          : 'border-light-200 dark:border-dark-700 hover:border-oto-500/40 dark:hover:border-oto-500/40 hover:shadow-oto-500/5'
      }`}
    >
      {/* Gradient overlay on hover */}
      <div className={`absolute inset-0 bg-gradient-to-br ${gradientClass} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />

      {/* Selected state inner glow */}
      {isSelected && (
        <div className="absolute inset-0 rounded-xl pointer-events-none bg-oto-500/5 animate-pulse" />
      )}

      {/* Badges */}
      <div className="absolute top-3 right-3 flex items-center gap-1.5 z-10">
        {software.is_featured && (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-yellow-500/10 border border-yellow-500/20 text-yellow-500 text-xs font-medium">
            <Star size={12} className="fill-yellow-500" />
          </span>
        )}
        {software.os_family && (
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
            software.os_family === 'windows'
              ? 'bg-blue-500/10 border border-blue-500/20 text-blue-400'
              : 'bg-orange-500/10 border border-orange-500/20 text-orange-400'
          }`}>
            {software.os_family === 'windows' ? 'Win' : 'Linux'}
          </span>
        )}
      </div>

      {/* Checkbox */}
      {(selectionMode || isSelected) && (
        <button
          onClick={onToggle}
          className={`absolute top-3 left-3 w-6 h-6 rounded-md border-2 flex items-center justify-center transition-all z-10 ${
            isSelected
              ? 'bg-oto-500 border-oto-500 shadow-md shadow-oto-500/30'
              : 'border-gray-300 dark:border-dark-500 hover:border-oto-500 bg-white/80 dark:bg-dark-800/80 backdrop-blur-sm'
          }`}
        >
          {isSelected && <Check size={14} className="text-white" />}
        </button>
      )}

      <div className="relative p-4">
        {/* Header */}
        <div className="flex items-start gap-3 mb-3">
          <div className={`w-11 h-11 rounded-xl border flex items-center justify-center flex-shrink-0 ${accentClass} group-hover:scale-110 group-hover:shadow-lg group-hover:shadow-current/20 transition-all duration-300`}>
            <IconComponent size={22} />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-bold text-sm text-gray-900 dark:text-white truncate group-hover:text-oto-600 dark:group-hover:text-oto-400 transition-colors">
              {software.display_name}
            </h3>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-gray-500 dark:text-dark-400 font-mono">
                {software.package_id}
              </span>
              {software.version && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-light-100 dark:bg-dark-700 text-gray-500 dark:text-dark-400">
                  v{software.version}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Description */}
        <p className="text-sm text-gray-500 dark:text-dark-400 line-clamp-2 mb-3 leading-relaxed">
          {software.short_description || software.description || 'Pas de description'}
        </p>

        {/* Tags */}
        <div className="flex flex-wrap gap-1 mb-3">
          {software.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs bg-light-100 dark:bg-dark-700/80 border border-light-200 dark:border-dark-600/60 text-gray-500 dark:text-dark-300 rounded-md font-medium hover:border-oto-500/30 hover:text-oto-600 dark:hover:text-oto-400 transition-colors cursor-default"
            >
              {tag}
            </span>
          ))}
          {software.tags.length > 3 && (
            <span className="px-2 py-0.5 text-xs border border-dashed border-light-300 dark:border-dark-600 text-gray-400 dark:text-dark-500 rounded-md">
              +{software.tags.length - 3}
            </span>
          )}
        </div>

        {/* Footer separator — gradient line */}
        <div className="h-px mb-3 bg-gradient-to-r from-transparent via-light-200 dark:via-dark-600 to-transparent" />

        {/* Footer */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs text-gray-400 dark:text-dark-500">
            <span className="flex items-center gap-1">
              <Clock size={13} />
              {software.install_time_minutes}min
            </span>
            {software.install_count > 0 && (
              <span className="flex items-center gap-1">
                <TrendingUp size={13} />
                {software.install_count}
              </span>
            )}
          </div>
          <div className="flex gap-1">
            <button
              onClick={onDetails}
              className="p-1.5 rounded-lg hover:bg-light-200 dark:hover:bg-dark-700 text-gray-400 dark:text-dark-400 hover:text-gray-700 dark:hover:text-white transition-all duration-150 hover:scale-110 active:scale-95"
              title="Voir les détails"
            >
              <Info size={18} />
            </button>
            <button
              onClick={onToggle}
              className={`p-1.5 rounded-lg transition-all duration-150 hover:scale-110 active:scale-95 ${
                isSelected
                  ? 'bg-oto-500 text-white shadow-md shadow-oto-500/30 hover:bg-oto-600'
                  : 'hover:bg-oto-500/10 dark:hover:bg-oto-500/15 text-gray-400 dark:text-dark-400 hover:text-oto-500 dark:hover:text-oto-400 border border-transparent hover:border-oto-500/30'
              }`}
              title={isSelected ? 'Désélectionner' : 'Sélectionner'}
            >
              {isSelected ? <Check size={18} /> : <Download size={18} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Software list item component
function SoftwareListItem({
  software,
  isSelected,
  onToggle,
  onDetails,
}: SoftwareCardProps) {
  const IconComponent = CATEGORY_LUCIDE[software.category] || Package;
  const accentClass = CATEGORY_ACCENT[software.category] || CATEGORY_ACCENT.other;
  const borderClass = CATEGORY_BORDER[software.category] || CATEGORY_BORDER.other;

  return (
    <div
      className={`group flex items-center gap-4 p-4 bg-white dark:bg-dark-800 rounded-xl border-l-4 border border-l-transparent transition-all duration-200 hover:shadow-lg hover:-translate-y-px ${
        isSelected
          ? `${borderClass} border-oto-500/30 ring-1 ring-oto-500/20 shadow-md shadow-oto-500/10 bg-oto-500/5 dark:bg-oto-500/5`
          : 'border-light-200 dark:border-dark-700 hover:border-oto-500/30 dark:hover:border-oto-500/30 hover:bg-light-50 dark:hover:bg-dark-750'
      }`}
    >
      {/* Checkbox */}
      <button
        onClick={onToggle}
        className={`w-6 h-6 rounded-md border-2 flex-shrink-0 flex items-center justify-center transition-all ${
          isSelected
            ? 'bg-oto-500 border-oto-500 shadow-sm shadow-oto-500/40'
            : 'border-gray-300 dark:border-dark-500 hover:border-oto-500 group-hover:border-oto-500/60'
        }`}
      >
        {isSelected && <Check size={14} className="text-white" />}
      </button>

      {/* Icon */}
      <div className={`w-11 h-11 rounded-xl border-2 flex items-center justify-center flex-shrink-0 transition-transform duration-200 group-hover:scale-105 ${accentClass}`}>
        <IconComponent size={20} />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-bold text-sm text-gray-900 dark:text-white leading-tight">{software.display_name}</h3>
          {software.version && (
            <span className="text-xs px-1.5 py-0.5 rounded-md bg-light-100 dark:bg-dark-700 text-gray-500 dark:text-dark-400 font-mono">
              v{software.version}
            </span>
          )}
          {software.is_featured && (
            <Star size={13} className="text-yellow-400 fill-yellow-400 flex-shrink-0" />
          )}
          {software.os_family && (
            <span className={`px-1.5 py-0.5 rounded text-xs font-semibold ${
              software.os_family === 'windows'
                ? 'bg-blue-500/10 text-blue-400'
                : 'bg-orange-500/10 text-orange-400'
            }`}>
              {software.os_family === 'windows' ? 'Win' : 'Linux'}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 dark:text-dark-400 truncate mt-1">
          {software.short_description || software.description}
        </p>
      </div>

      {/* Tags */}
      <div className="hidden lg:flex flex-wrap gap-1 max-w-[200px]">
        {software.tags.slice(0, 2).map((tag) => (
          <span
            key={tag}
            className="px-2 py-0.5 text-xs bg-light-100 dark:bg-dark-700 text-gray-500 dark:text-dark-400 rounded-md font-medium"
          >
            {tag}
          </span>
        ))}
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 text-xs text-gray-400 dark:text-dark-500 flex-shrink-0">
        <span className="flex items-center gap-1">
          <Clock size={13} />
          {software.install_time_minutes}min
        </span>
        {software.install_count > 0 && (
          <span className="flex items-center gap-1">
            <TrendingUp size={13} />
            {software.install_count}
          </span>
        )}
      </div>

      {/* Actions — Details button reveals label on group hover */}
      <button
        onClick={onDetails}
        className="flex items-center gap-1.5 pl-2 pr-3 py-1.5 rounded-lg hover:bg-light-200 dark:hover:bg-dark-700 text-gray-400 dark:text-dark-400 hover:text-gray-700 dark:hover:text-white transition-all duration-200 overflow-hidden"
      >
        <Info size={16} className="flex-shrink-0" />
        <span className="text-xs font-medium max-w-0 group-hover:max-w-[3rem] overflow-hidden transition-all duration-200 whitespace-nowrap opacity-0 group-hover:opacity-100">
          Détails
        </span>
      </button>
    </div>
  );
}

// Details modal
interface SoftwareDetailsModalProps {
  software: SoftwarePackage;
  isOpen: boolean;
  onClose: () => void;
  isSelected: boolean;
  onToggle: () => void;
}

function SoftwareDetailsModal({
  software,
  isOpen,
  onClose,
  isSelected,
  onToggle,
}: SoftwareDetailsModalProps) {
  const [copied, setCopied] = useState(false);
  const IconComponent = CATEGORY_LUCIDE[software.category] || Package;
  const accentClass = CATEGORY_ACCENT[software.category] || CATEGORY_ACCENT.other;
  const gradientClass = CATEGORY_GRADIENT[software.category] || CATEGORY_GRADIENT.other;
  const glowClass = CATEGORY_GLOW[software.category] || CATEGORY_GLOW.other;
  const dotClass = CATEGORY_DOT[software.category] || CATEGORY_DOT.other;

  const configJson = JSON.stringify(software.default_config, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(configJson).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  // Helper: render a section title with colored dot accent
  const SectionTitle = ({ children }: { children: ReactNode }) => (
    <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-dark-300 mb-3 uppercase tracking-wide">
      <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${dotClass}`} />
      {children}
    </h3>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={software.display_name} size="lg">
      <div className="space-y-6">
        {/* Header with deeper gradient + subtle dot-grid pattern overlay */}
        <div className={`relative -mx-6 -mt-4 px-6 py-7 bg-gradient-to-br ${gradientClass} overflow-hidden`}>
          {/* Dot-grid pattern overlay */}
          <div
            className="absolute inset-0 opacity-[0.06] dark:opacity-[0.10]"
            style={{
              backgroundImage: 'radial-gradient(circle, currentColor 1px, transparent 1px)',
              backgroundSize: '18px 18px',
            }}
          />
          <div className="relative flex items-start gap-5">
            {/* Icon with glow shadow */}
            <div className={`w-18 h-18 min-w-[4.5rem] min-h-[4.5rem] rounded-2xl border-2 flex items-center justify-center shadow-lg ${glowClass} ${accentClass} transition-transform duration-300 hover:scale-105`}>
              <IconComponent size={34} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-extrabold text-gray-900 dark:text-white tracking-tight">{software.display_name}</h2>
                {software.version && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-white/60 dark:bg-dark-700/80 text-gray-600 dark:text-dark-300 font-mono border border-gray-200/60 dark:border-dark-600/60 backdrop-blur-sm">
                    v{software.version}
                  </span>
                )}
                {software.is_featured && (
                  <span className="flex items-center gap-1 px-2 py-0.5 text-xs bg-yellow-500/15 text-yellow-600 dark:text-yellow-400 rounded-full border border-yellow-500/30 font-semibold">
                    <Star size={11} className="fill-current" />
                    Recommandé
                  </span>
                )}
                {software.os_family && (
                  <span className={`px-2 py-0.5 text-xs rounded-full font-semibold ${
                    software.os_family === 'windows'
                      ? 'bg-blue-500/15 border border-blue-500/30 text-blue-500 dark:text-blue-400'
                      : 'bg-orange-500/15 border border-orange-500/30 text-orange-500 dark:text-orange-400'
                  }`}>
                    {software.os_family === 'windows' ? 'Windows' : 'Linux'}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 dark:text-dark-400 font-mono mt-1.5 opacity-80">{software.package_id}</p>
              {software.website && (
                <a
                  href={software.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-oto-500 hover:text-oto-400 mt-1.5 transition-colors font-medium"
                >
                  <ExternalLink size={13} />
                  Site officiel
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Description */}
        <div>
          <SectionTitle>Description</SectionTitle>
          <p className="text-gray-600 dark:text-dark-400 leading-relaxed text-sm">
            {software.description || 'Pas de description disponible.'}
          </p>
        </div>

        {/* Stats grid — with hover scale effect */}
        <div className="grid grid-cols-3 gap-3">
          <div className="group/stat bg-light-50 dark:bg-dark-700/50 rounded-xl p-4 text-center border border-light-200/60 dark:border-dark-600/40 transition-all duration-200 hover:scale-[1.03] hover:shadow-md hover:border-oto-500/30 cursor-default">
            <Package size={20} className="mx-auto text-gray-400 dark:text-dark-400 mb-1.5 group-hover/stat:text-oto-500 transition-colors" />
            <span className="text-xs text-gray-500 dark:text-dark-400 block mb-0.5">Gestionnaire</span>
            <p className="text-sm font-bold text-gray-900 dark:text-white">{software.package_manager}</p>
          </div>
          <div className="group/stat bg-light-50 dark:bg-dark-700/50 rounded-xl p-4 text-center border border-light-200/60 dark:border-dark-600/40 transition-all duration-200 hover:scale-[1.03] hover:shadow-md hover:border-oto-500/30 cursor-default">
            <Clock size={20} className="mx-auto text-gray-400 dark:text-dark-400 mb-1.5 group-hover/stat:text-oto-500 transition-colors" />
            <span className="text-xs text-gray-500 dark:text-dark-400 block mb-0.5">Installation</span>
            <p className="text-sm font-bold text-gray-900 dark:text-white">{software.install_time_minutes} min</p>
          </div>
          <div className="group/stat bg-light-50 dark:bg-dark-700/50 rounded-xl p-4 text-center border border-light-200/60 dark:border-dark-600/40 transition-all duration-200 hover:scale-[1.03] hover:shadow-md hover:border-oto-500/30 cursor-default">
            <TrendingUp size={20} className="mx-auto text-gray-400 dark:text-dark-400 mb-1.5 group-hover/stat:text-oto-500 transition-colors" />
            <span className="text-xs text-gray-500 dark:text-dark-400 block mb-0.5">Installations</span>
            <p className="text-sm font-bold text-gray-900 dark:text-white">{software.install_count}</p>
          </div>
        </div>

        {/* Tags */}
        {software.tags.length > 0 && (
          <div>
            <SectionTitle>Tags</SectionTitle>
            <div className="flex flex-wrap gap-2">
              {software.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-3 py-1 text-xs bg-light-100 dark:bg-dark-700 text-gray-600 dark:text-dark-300 rounded-lg font-medium border border-light-200 dark:border-dark-600 hover:bg-light-200 dark:hover:bg-dark-600 transition-colors"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Dependencies */}
        {software.dependencies.length > 0 && (
          <div>
            <SectionTitle>Dépendances</SectionTitle>
            <div className="flex flex-wrap gap-2">
              {software.dependencies.map((dep) => (
                <span
                  key={dep}
                  className="px-3 py-1 text-xs bg-oto-500/10 text-oto-500 rounded-lg font-semibold border border-oto-500/20 hover:bg-oto-500/20 transition-colors"
                >
                  {dep}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Conflicts */}
        {software.conflicts.length > 0 && (
          <div>
            <SectionTitle>Conflits</SectionTitle>
            <div className="flex flex-wrap gap-2">
              {software.conflicts.map((conflict) => (
                <span
                  key={conflict}
                  className="px-3 py-1 text-xs bg-red-500/10 text-red-400 rounded-lg font-semibold border border-red-500/20 hover:bg-red-500/20 transition-colors"
                >
                  {conflict}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Default config — with copy button and line numbers */}
        {Object.keys(software.default_config).length > 0 && (
          <div>
            <SectionTitle>Configuration par défaut</SectionTitle>
            <div className="relative rounded-xl overflow-hidden border border-dark-700 bg-[#0d1117]">
              {/* Toolbar */}
              <div className="flex items-center justify-between px-4 py-2 bg-dark-800/80 border-b border-dark-700">
                <span className="text-xs font-mono text-dark-400 flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-full bg-red-500/70 inline-block" />
                  <span className="w-3 h-3 rounded-full bg-yellow-500/70 inline-block" />
                  <span className="w-3 h-3 rounded-full bg-green-500/70 inline-block" />
                  <span className="ml-2 opacity-60">config.json</span>
                </span>
                <button
                  onClick={handleCopy}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-200 ${
                    copied
                      ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                      : 'bg-dark-700 text-dark-300 border border-dark-600 hover:bg-dark-600 hover:text-white'
                  }`}
                >
                  {copied ? <CheckCheck size={12} /> : <Copy size={12} />}
                  {copied ? 'Copié !' : 'Copier'}
                </button>
              </div>
              {/* Code with line numbers */}
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono">
                  <tbody>
                    {configJson.split('\n').map((line, i) => (
                      <tr key={i} className="hover:bg-white/[0.03] transition-colors">
                        <td className="select-none text-right px-3 py-0.5 text-dark-500 border-r border-dark-700 w-8 text-[11px]">
                          {i + 1}
                        </td>
                        <td className="px-4 py-0.5 whitespace-pre text-[#e6edf3]">
                          {line
                            .replace(/("([^"]+)")\s*:/g, (_m: string, _full: string, key: string) =>
                              `<span style="color:#79c0ff">"${key}"</span>:`
                            )
                            .split(/(<span[^>]*>.*?<\/span>:?)/g)
                            .map((part: string, j: number) =>
                              part.startsWith('<span') ? (
                                <span
                                  key={j}
                                  dangerouslySetInnerHTML={{ __html: part }}
                                />
                              ) : (
                                <span key={j} style={{ color: part.match(/^\s*"/) ? '#a5d6ff' : part.match(/^\s*(true|false|null)/) ? '#ff7b72' : part.match(/^\s*[0-9]/) ? '#f8cc62' : '#e6edf3' }}>
                                  {part}
                                </span>
                              )
                            )
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-4 border-t border-light-200 dark:border-dark-700">
          <Button variant="ghost" onClick={onClose} className="px-5">
            Fermer
          </Button>
          <Button
            variant={isSelected ? 'secondary' : 'primary'}
            onClick={() => {
              onToggle();
              onClose();
            }}
            leftIcon={isSelected ? <Check size={16} /> : <Download size={16} />}
            className="px-6 font-semibold"
          >
            {isSelected ? 'Sélectionné' : 'Sélectionner'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default Marketplace;
