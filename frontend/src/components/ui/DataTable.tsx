import { useState, useMemo, type ReactNode } from 'react';
import {
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  ChevronLeft,
  ChevronRight,
  Search,
} from 'lucide-react';
import { Button } from './Button';

export interface Column<T> {
  key: keyof T | string;
  header: string;
  sortable?: boolean;
  render?: (item: T) => ReactNode;
  width?: string;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  keyExtractor: (item: T) => string;
  isLoading?: boolean;
  emptyMessage?: string;
  emptyIcon?: ReactNode;
  searchable?: boolean;
  searchPlaceholder?: string;
  searchKeys?: (keyof T)[];
  pageSize?: number;
  actions?: (item: T) => ReactNode;
  onRowClick?: (item: T) => void;
}

type SortDirection = 'asc' | 'desc' | null;

export function DataTable<T extends object>({
  data,
  columns,
  keyExtractor,
  isLoading = false,
  emptyMessage = 'Aucune donnée',
  emptyIcon,
  searchable = false,
  searchPlaceholder = 'Rechercher...',
  searchKeys = [],
  pageSize = 10,
  actions,
  onRowClick,
}: DataTableProps<T>) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [currentPage, setCurrentPage] = useState(1);

  // Filter data based on search
  const filteredData = useMemo(() => {
    if (!search || searchKeys.length === 0) return data;
    const searchLower = search.toLowerCase();
    return data.filter((item) =>
      searchKeys.some((key) => {
        const value = item[key];
        return value && String(value).toLowerCase().includes(searchLower);
      })
    );
  }, [data, search, searchKeys]);

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortKey || !sortDirection) return filteredData;
    return [...filteredData].sort((a, b) => {
      const aVal = a[sortKey as keyof T];
      const bVal = b[sortKey as keyof T];
      if (aVal === bVal) return 0;
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      const comparison = aVal < bVal ? -1 : 1;
      return sortDirection === 'asc' ? comparison : -comparison;
    });
  }, [filteredData, sortKey, sortDirection]);

  // Paginate data
  const totalPages = Math.ceil(sortedData.length / pageSize);
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, currentPage, pageSize]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      if (sortDirection === 'asc') setSortDirection('desc');
      else if (sortDirection === 'desc') {
        setSortKey(null);
        setSortDirection(null);
      }
    } else {
      setSortKey(key);
      setSortDirection('asc');
    }
  };

  const getSortIcon = (key: string) => {
    if (sortKey !== key) return <ChevronsUpDown size={14} className="text-dark-500" />;
    if (sortDirection === 'asc') return <ChevronUp size={14} className="text-primary-500" />;
    return <ChevronDown size={14} className="text-primary-500" />;
  };

  // Reset to page 1 when search changes
  const handleSearch = (value: string) => {
    setSearch(value);
    setCurrentPage(1);
  };

  return (
    <div className="card">
      {/* Search bar */}
      {searchable && (
        <div className="p-4 border-b border-dark-700">
          <div className="relative max-w-sm">
            <Search
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-dark-400"
            />
            <input
              type="text"
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full pl-10 pr-4 py-2 bg-dark-700 border border-dark-600 rounded-lg text-dark-100 placeholder-dark-400 focus:outline-none focus:border-primary-500 transition-colors"
            />
          </div>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-dark-400 text-sm border-b border-dark-700 bg-dark-800/50">
              {columns.map((column) => (
                <th
                  key={String(column.key)}
                  className="px-4 py-3 font-medium"
                  style={{ width: column.width }}
                >
                  {column.sortable ? (
                    <button
                      onClick={() => handleSort(String(column.key))}
                      className="flex items-center gap-1 hover:text-white transition-colors"
                    >
                      {column.header}
                      {getSortIcon(String(column.key))}
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              ))}
              {actions && <th className="px-4 py-3 font-medium w-24">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              // Loading skeleton
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-dark-700/50">
                  {columns.map((column) => (
                    <td key={String(column.key)} className="px-4 py-3">
                      <div className="h-5 bg-dark-700 rounded animate-pulse" />
                    </td>
                  ))}
                  {actions && (
                    <td className="px-4 py-3">
                      <div className="h-5 w-16 bg-dark-700 rounded animate-pulse" />
                    </td>
                  )}
                </tr>
              ))
            ) : paginatedData.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + (actions ? 1 : 0)}
                  className="px-4 py-12 text-center"
                >
                  <div className="flex flex-col items-center text-dark-400">
                    {emptyIcon}
                    <p className="mt-2">{emptyMessage}</p>
                  </div>
                </td>
              </tr>
            ) : (
              paginatedData.map((item) => (
                <tr
                  key={keyExtractor(item)}
                  onClick={() => onRowClick?.(item)}
                  className={`border-b border-dark-700/50 hover:bg-dark-800/50 transition-colors ${
                    onRowClick ? 'cursor-pointer' : ''
                  }`}
                >
                  {columns.map((column) => (
                    <td key={String(column.key)} className="px-4 py-3 text-dark-200">
                      {column.render
                        ? column.render(item)
                        : String(item[column.key as keyof T] ?? '-')}
                    </td>
                  ))}
                  {actions && (
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      {actions(item)}
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-dark-700">
          <p className="text-sm text-dark-400">
            Affichage {(currentPage - 1) * pageSize + 1} -{' '}
            {Math.min(currentPage * pageSize, sortedData.length)} sur {sortedData.length}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              <ChevronLeft size={16} />
            </Button>
            <span className="text-sm text-dark-300">
              Page {currentPage} / {totalPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
            >
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
