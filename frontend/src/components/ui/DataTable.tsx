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
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  pageSize?: number;
  actions?: (item: T) => ReactNode;
  onRowClick?: (item: T) => void;
  selectable?: boolean;
  selectedKeys?: Set<string>;
  onSelectionChange?: (selectedKeys: Set<string>) => void;
  bulkActions?: ReactNode;
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
  searchValue,
  onSearchChange,
  pageSize = 10,
  actions,
  onRowClick,
  selectable = false,
  selectedKeys,
  onSelectionChange,
  bulkActions,
}: DataTableProps<T>) {
  const [internalSearch, setInternalSearch] = useState('');
  const isControlled = searchValue !== undefined;
  const search = isControlled ? searchValue : internalSearch;
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
    if (sortKey !== key) return <ChevronsUpDown size={14} className="text-gray-400 dark:text-dark-500" />;
    if (sortDirection === 'asc') return <ChevronUp size={14} className="text-oto-500" />;
    return <ChevronDown size={14} className="text-oto-500" />;
  };

  // Selection helpers
  const allPageKeys = paginatedData.map(keyExtractor);
  const allPageSelected = selectable && selectedKeys && allPageKeys.length > 0 && allPageKeys.every((k) => selectedKeys.has(k));
  const somePageSelected = selectable && selectedKeys && allPageKeys.some((k) => selectedKeys.has(k));
  const selectionCount = selectedKeys?.size ?? 0;

  const toggleAll = () => {
    if (!onSelectionChange || !selectedKeys) return;
    const next = new Set(selectedKeys);
    if (allPageSelected) {
      allPageKeys.forEach((k) => next.delete(k));
    } else {
      allPageKeys.forEach((k) => next.add(k));
    }
    onSelectionChange(next);
  };

  const toggleOne = (key: string) => {
    if (!onSelectionChange || !selectedKeys) return;
    const next = new Set(selectedKeys);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    onSelectionChange(next);
  };

  // Reset to page 1 when search changes
  const handleSearch = (value: string) => {
    if (isControlled && onSearchChange) {
      onSearchChange(value);
    } else {
      setInternalSearch(value);
    }
    setCurrentPage(1);
  };

  return (
    <div className="card">
      {/* Search bar */}
      {searchable && (
        <div className="p-4 border-b border-light-200 dark:border-dark-700">
          <div className="relative max-w-sm">
            <Search
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-400"
            />
            <input
              type="text"
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full pl-10 pr-4 py-2 bg-light-100 dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-lg text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-oto-500 focus:border-transparent transition-all"
            />
          </div>
        </div>
      )}

      {/* Bulk actions bar */}
      {selectable && selectionCount > 0 && bulkActions && (
        <div className="px-4 py-3 bg-oto-50 dark:bg-oto-900/20 border-b border-oto-200 dark:border-oto-800/30 flex items-center gap-3">
          <span className="text-sm font-medium text-oto-700 dark:text-oto-300">
            {selectionCount} sélectionné{selectionCount > 1 ? 's' : ''}
          </span>
          <div className="h-4 w-px bg-oto-300 dark:bg-oto-700" />
          {bulkActions}
          <button
            onClick={() => onSelectionChange?.(new Set())}
            className="ml-auto text-sm text-gray-500 dark:text-dark-400 hover:text-gray-700 dark:hover:text-dark-200 transition-colors"
          >
            Tout désélectionner
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-oto-700 dark:text-dark-400 text-sm border-b border-light-200 dark:border-dark-700 bg-oto-50 dark:bg-dark-800/50">
              {selectable && (
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={allPageSelected}
                    ref={(el) => { if (el) el.indeterminate = !allPageSelected && !!somePageSelected; }}
                    onChange={toggleAll}
                    className="w-4 h-4 rounded border-gray-300 dark:border-dark-500 text-oto-600 focus:ring-oto-500 cursor-pointer"
                  />
                </th>
              )}
              {columns.map((column) => (
                <th
                  key={String(column.key)}
                  className="px-4 py-3 font-medium"
                  style={{ width: column.width }}
                >
                  {column.sortable ? (
                    <button
                      onClick={() => handleSort(String(column.key))}
                      className="flex items-center gap-1 hover:text-oto-600 dark:hover:text-white transition-colors uppercase tracking-wide"
                    >
                      {column.header}
                      {getSortIcon(String(column.key))}
                    </button>
                  ) : (
                    <span className="uppercase tracking-wide">{column.header}</span>
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
                <tr key={i} className="border-b border-light-200 dark:border-dark-700/50">
                  {selectable && (
                    <td className="px-4 py-3">
                      <div className="h-4 w-4 bg-light-200 dark:bg-dark-700 rounded animate-pulse" />
                    </td>
                  )}
                  {columns.map((column) => (
                    <td key={String(column.key)} className="px-4 py-3">
                      <div className="h-5 bg-light-200 dark:bg-dark-700 rounded animate-pulse" />
                    </td>
                  ))}
                  {actions && (
                    <td className="px-4 py-3">
                      <div className="h-5 w-16 bg-light-200 dark:bg-dark-700 rounded animate-pulse" />
                    </td>
                  )}
                </tr>
              ))
            ) : paginatedData.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + (actions ? 1 : 0) + (selectable ? 1 : 0)}
                  className="px-4 py-12 text-center"
                >
                  <div className="flex flex-col items-center text-gray-400 dark:text-dark-400">
                    {emptyIcon}
                    <p className="mt-2">{emptyMessage}</p>
                  </div>
                </td>
              </tr>
            ) : (
              paginatedData.map((item, index) => {
                const itemKey = keyExtractor(item);
                const isSelected = selectable && selectedKeys?.has(itemKey);
                return (
                <tr
                  key={itemKey}
                  onClick={() => onRowClick?.(item)}
                  className={`border-b border-light-200 dark:border-dark-700/50 hover:bg-oto-50 dark:hover:bg-dark-800/50 transition-colors ${
                    onRowClick ? 'cursor-pointer' : ''
                  } ${isSelected ? 'bg-oto-50/50 dark:bg-oto-900/10' : index % 2 === 1 ? 'bg-light-50 dark:bg-dark-800/20' : ''}`}
                >
                  {selectable && (
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSelected || false}
                        onChange={() => toggleOne(itemKey)}
                        className="w-4 h-4 rounded border-gray-300 dark:border-dark-500 text-oto-600 focus:ring-oto-500 cursor-pointer"
                      />
                    </td>
                  )}
                  {columns.map((column) => (
                    <td key={String(column.key)} className="px-4 py-3 text-gray-700 dark:text-dark-200">
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
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-light-200 dark:border-dark-700">
          <p className="text-sm text-gray-500 dark:text-dark-400">
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
            <span className="text-sm text-gray-600 dark:text-dark-300 font-medium">
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
