import { useState, useEffect, useMemo } from 'react';
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  Squares2X2Icon,
  ListBulletIcon,
  StarIcon,
  ClockIcon,
  ArrowDownTrayIcon,
  CheckIcon,
  XMarkIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline';
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid';
import { softwareApi } from '../services/api';
import type { SoftwarePackage, SoftwareCategory_Info, SoftwareProfile } from '../types';
import { Button, Input, Modal, Skeleton, StatusBadge } from '../components/ui';

// Mapping des icônes par catégorie
const CATEGORY_ICONS: Record<string, string> = {
  windows_role: '🖥️',
  remote_access: '🔐',
  database: '🗄️',
  webserver: '🌐',
  development: '👨‍💻',
  runtime: '⚡',
  monitoring: '📊',
  security: '🛡️',
  utilities: '🔧',
  browser: '🌍',
  containers: '📦',
  file_transfer: '🔄',
  network: '📡',
  backup: '💾',
  other: '📁',
};

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
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [detailsModal, setDetailsModal] = useState<SoftwarePackage | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set(selectedPackages));

  // Charger les données
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [softwareData, categoriesData, profilesData] = await Promise.all([
          softwareApi.list({ page_size: 200 }),
          softwareApi.getCategories(),
          softwareApi.getProfiles(),
        ]);
        setSoftware(softwareData.items);
        setCategories(categoriesData);
        setProfiles(profilesData.profiles);
      } catch (error) {
        console.error('Erreur chargement marketplace:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // Filtrer les logiciels
  const filteredSoftware = useMemo(() => {
    return software.filter((pkg) => {
      // Filtre par catégorie
      if (selectedCategory !== 'all' && pkg.category !== selectedCategory) {
        return false;
      }

      // Filtre par recherche
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        return (
          pkg.name.toLowerCase().includes(query) ||
          pkg.display_name.toLowerCase().includes(query) ||
          pkg.description?.toLowerCase().includes(query) ||
          pkg.tags.some((tag) => tag.toLowerCase().includes(query))
        );
      }

      return true;
    });
  }, [software, selectedCategory, searchQuery]);

  // Gérer la sélection
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

  // Sélectionner un profil
  const selectProfile = (profile: SoftwareProfile) => {
    const newSelected = new Set(profile.packages);
    setSelected(newSelected);
    onSelectionChange?.(profile.packages);
  };

  // Désélectionner tout
  const clearSelection = () => {
    setSelected(new Set());
    onSelectionChange?.([]);
  };

  // Initialiser le catalogue
  const handleSeedCatalog = async () => {
    try {
      const result = await softwareApi.seedCatalog();
      alert(`Catalogue initialisé: ${result.created} créés, ${result.skipped} ignorés`);
      // Recharger
      const softwareData = await softwareApi.list({ page_size: 200 });
      setSoftware(softwareData.items);
    } catch (error) {
      console.error('Erreur seed:', error);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">
            {selectionMode ? 'Sélectionner les logiciels' : 'Marketplace Logiciels'}
          </h1>
          <p className="mt-1 text-sm text-gray-400">
            {software.length} logiciels disponibles
            {selected.size > 0 && ` • ${selected.size} sélectionnés`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {!selectionMode && software.length === 0 && (
            <Button onClick={handleSeedCatalog}>
              Initialiser le catalogue
            </Button>
          )}
          {selected.size > 0 && (
            <Button variant="ghost" onClick={clearSelection}>
              <XMarkIcon className="h-4 w-4 mr-1" />
              Tout désélectionner
            </Button>
          )}
        </div>
      </div>

      {/* Profils pré-définis */}
      {profiles.length > 0 && (
        <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
          <h2 className="text-lg font-semibold text-white mb-3">Profils pré-configurés</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {profiles.map((profile) => (
              <button
                key={profile.name}
                onClick={() => selectProfile(profile)}
                className="flex flex-col items-center p-3 rounded-lg bg-gray-700/50 hover:bg-gray-700 border border-gray-600 hover:border-blue-500 transition-all group"
              >
                <span className="text-2xl mb-1">{CATEGORY_ICONS[profile.name] || '📦'}</span>
                <span className="text-sm font-medium text-white group-hover:text-blue-400">
                  {profile.display_name}
                </span>
                <span className="text-xs text-gray-400 mt-1">
                  {profile.package_count} packages
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Barre de recherche et filtres */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
          <Input
            type="text"
            placeholder="Rechercher un logiciel..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
          >
            <option value="all">Toutes les catégories</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {CATEGORY_ICONS[cat.id] || ''} {cat.name} ({cat.count})
              </option>
            ))}
          </select>
          <div className="flex rounded-lg border border-gray-600 overflow-hidden">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-2 ${viewMode === 'grid' ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'}`}
            >
              <Squares2X2Icon className="h-5 w-5 text-white" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-2 ${viewMode === 'list' ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'}`}
            >
              <ListBulletIcon className="h-5 w-5 text-white" />
            </button>
          </div>
        </div>
      </div>

      {/* Catégories (horizontal scroll) */}
      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-gray-600">
        <button
          onClick={() => setSelectedCategory('all')}
          className={`px-4 py-2 rounded-full whitespace-nowrap text-sm font-medium transition-colors ${
            selectedCategory === 'all'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          Tous ({software.length})
        </button>
        {categories.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setSelectedCategory(cat.id)}
            className={`px-4 py-2 rounded-full whitespace-nowrap text-sm font-medium transition-colors flex items-center gap-1 ${
              selectedCategory === cat.id
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            <span>{CATEGORY_ICONS[cat.id] || '📁'}</span>
            {cat.name}
            <span className="text-xs opacity-70">({cat.count})</span>
          </button>
        ))}
      </div>

      {/* Liste des logiciels */}
      {filteredSoftware.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-400">Aucun logiciel trouvé</p>
        </div>
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

      {/* Modal détails */}
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
  );
}

// Composant carte logiciel
interface SoftwareCardProps {
  software: SoftwarePackage;
  isSelected: boolean;
  onToggle: () => void;
  onDetails: () => void;
  selectionMode: boolean;
}

function SoftwareCard({ software, isSelected, onToggle, onDetails, selectionMode }: SoftwareCardProps) {
  return (
    <div
      className={`relative bg-gray-800 rounded-xl border transition-all hover:shadow-lg ${
        isSelected
          ? 'border-blue-500 ring-2 ring-blue-500/20'
          : 'border-gray-700 hover:border-gray-600'
      }`}
    >
      {/* Badge featured */}
      {software.is_featured && (
        <div className="absolute top-2 right-2">
          <StarIconSolid className="h-5 w-5 text-yellow-400" />
        </div>
      )}

      {/* Checkbox si mode sélection */}
      {(selectionMode || isSelected) && (
        <button
          onClick={onToggle}
          className={`absolute top-2 left-2 w-6 h-6 rounded-md border-2 flex items-center justify-center transition-all ${
            isSelected
              ? 'bg-blue-600 border-blue-600'
              : 'border-gray-500 hover:border-blue-500'
          }`}
        >
          {isSelected && <CheckIcon className="h-4 w-4 text-white" />}
        </button>
      )}

      <div className="p-4">
        {/* Header avec icône et nom */}
        <div className="flex items-start gap-3 mb-3">
          <div className="w-10 h-10 rounded-lg bg-gray-700 flex items-center justify-center text-xl">
            {CATEGORY_ICONS[software.category] || '📦'}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-white truncate">{software.display_name}</h3>
            <p className="text-xs text-gray-400">{software.package_id}</p>
          </div>
        </div>

        {/* Description */}
        <p className="text-sm text-gray-400 line-clamp-2 mb-3">
          {software.short_description || software.description || 'Pas de description'}
        </p>

        {/* Tags */}
        <div className="flex flex-wrap gap-1 mb-3">
          {software.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs bg-gray-700 text-gray-300 rounded-full"
            >
              {tag}
            </span>
          ))}
          {software.tags.length > 3 && (
            <span className="px-2 py-0.5 text-xs text-gray-400">
              +{software.tags.length - 3}
            </span>
          )}
        </div>

        {/* Footer avec temps et actions */}
        <div className="flex items-center justify-between pt-3 border-t border-gray-700">
          <div className="flex items-center text-xs text-gray-400">
            <ClockIcon className="h-4 w-4 mr-1" />
            {software.install_time_minutes} min
          </div>
          <div className="flex gap-2">
            <button
              onClick={onDetails}
              className="p-1.5 rounded-lg hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
            >
              <InformationCircleIcon className="h-5 w-5" />
            </button>
            <button
              onClick={onToggle}
              className={`p-1.5 rounded-lg transition-colors ${
                isSelected
                  ? 'bg-blue-600 text-white'
                  : 'hover:bg-gray-700 text-gray-400 hover:text-white'
              }`}
            >
              {isSelected ? (
                <CheckIcon className="h-5 w-5" />
              ) : (
                <ArrowDownTrayIcon className="h-5 w-5" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Composant liste logiciel
function SoftwareListItem({
  software,
  isSelected,
  onToggle,
  onDetails,
  selectionMode,
}: SoftwareCardProps) {
  return (
    <div
      className={`flex items-center gap-4 p-4 bg-gray-800 rounded-lg border transition-all ${
        isSelected
          ? 'border-blue-500 ring-1 ring-blue-500/20'
          : 'border-gray-700 hover:border-gray-600'
      }`}
    >
      {/* Checkbox */}
      <button
        onClick={onToggle}
        className={`w-6 h-6 rounded-md border-2 flex-shrink-0 flex items-center justify-center transition-all ${
          isSelected
            ? 'bg-blue-600 border-blue-600'
            : 'border-gray-500 hover:border-blue-500'
        }`}
      >
        {isSelected && <CheckIcon className="h-4 w-4 text-white" />}
      </button>

      {/* Icône */}
      <div className="w-10 h-10 rounded-lg bg-gray-700 flex items-center justify-center text-xl flex-shrink-0">
        {CATEGORY_ICONS[software.category] || '📦'}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-white">{software.display_name}</h3>
          {software.is_featured && <StarIconSolid className="h-4 w-4 text-yellow-400" />}
        </div>
        <p className="text-sm text-gray-400 truncate">
          {software.short_description || software.description}
        </p>
      </div>

      {/* Tags */}
      <div className="hidden lg:flex flex-wrap gap-1 max-w-[200px]">
        {software.tags.slice(0, 2).map((tag) => (
          <span
            key={tag}
            className="px-2 py-0.5 text-xs bg-gray-700 text-gray-300 rounded-full"
          >
            {tag}
          </span>
        ))}
      </div>

      {/* Temps */}
      <div className="flex items-center text-xs text-gray-400 flex-shrink-0">
        <ClockIcon className="h-4 w-4 mr-1" />
        {software.install_time_minutes} min
      </div>

      {/* Actions */}
      <button
        onClick={onDetails}
        className="p-2 rounded-lg hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
      >
        <InformationCircleIcon className="h-5 w-5" />
      </button>
    </div>
  );
}

// Modal détails
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
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={software.display_name} size="lg">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-xl bg-gray-700 flex items-center justify-center text-3xl">
            {CATEGORY_ICONS[software.category] || '📦'}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white">{software.display_name}</h2>
              {software.is_featured && (
                <span className="px-2 py-0.5 text-xs bg-yellow-500/20 text-yellow-400 rounded-full">
                  Recommandé
                </span>
              )}
            </div>
            <p className="text-sm text-gray-400">{software.package_id}</p>
            {software.website && (
              <a
                href={software.website}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-400 hover:text-blue-300"
              >
                Site officiel →
              </a>
            )}
          </div>
        </div>

        {/* Description */}
        <div>
          <h3 className="text-sm font-medium text-gray-300 mb-2">Description</h3>
          <p className="text-gray-400">{software.description || 'Pas de description disponible.'}</p>
        </div>

        {/* Infos techniques */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-800 rounded-lg p-3">
            <span className="text-xs text-gray-400">Gestionnaire</span>
            <p className="text-white font-medium">{software.package_manager}</p>
          </div>
          <div className="bg-gray-800 rounded-lg p-3">
            <span className="text-xs text-gray-400">Temps d'installation</span>
            <p className="text-white font-medium">{software.install_time_minutes} minutes</p>
          </div>
        </div>

        {/* Tags */}
        {software.tags.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-2">Tags</h3>
            <div className="flex flex-wrap gap-2">
              {software.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-3 py-1 text-sm bg-gray-700 text-gray-300 rounded-full"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Dépendances */}
        {software.dependencies.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-2">Dépendances</h3>
            <div className="flex flex-wrap gap-2">
              {software.dependencies.map((dep) => (
                <span
                  key={dep}
                  className="px-3 py-1 text-sm bg-blue-500/20 text-blue-400 rounded-full"
                >
                  {dep}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Configuration par défaut */}
        {Object.keys(software.default_config).length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-2">Configuration par défaut</h3>
            <div className="bg-gray-800 rounded-lg p-3 font-mono text-sm text-gray-300">
              <pre>{JSON.stringify(software.default_config, null, 2)}</pre>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-4 border-t border-gray-700">
          <Button variant="ghost" onClick={onClose}>
            Fermer
          </Button>
          <Button
            variant={isSelected ? 'secondary' : 'primary'}
            onClick={() => {
              onToggle();
              onClose();
            }}
          >
            {isSelected ? (
              <>
                <CheckIcon className="h-4 w-4 mr-2" />
                Sélectionné
              </>
            ) : (
              <>
                <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                Sélectionner
              </>
            )}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default Marketplace;
