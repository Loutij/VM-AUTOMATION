import { Bell, Search, User } from 'lucide-react';

interface HeaderProps {
  title: string;
}

export function Header({ title }: HeaderProps) {
  return (
    <header className="h-16 bg-dark-800 border-b border-dark-700 flex items-center justify-between px-6">
      {/* Titre de la page */}
      <h1 className="text-xl font-semibold text-white">{title}</h1>

      {/* Actions */}
      <div className="flex items-center gap-4">
        {/* Recherche */}
        <div className="relative">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-dark-400"
          />
          <input
            type="text"
            placeholder="Rechercher..."
            className="w-64 pl-10 pr-4 py-2 bg-dark-700 border border-dark-600 rounded-lg text-dark-100 placeholder-dark-400 focus:outline-none focus:border-primary-500 transition-colors"
          />
        </div>

        {/* Notifications */}
        <button className="relative p-2 text-dark-300 hover:text-white hover:bg-dark-700 rounded-lg transition-colors">
          <Bell size={20} />
          <span className="absolute top-1 right-1 w-2 h-2 bg-primary-500 rounded-full" />
        </button>

        {/* User menu */}
        <button className="flex items-center gap-2 p-2 text-dark-300 hover:text-white hover:bg-dark-700 rounded-lg transition-colors">
          <div className="w-8 h-8 bg-primary-600 rounded-full flex items-center justify-center">
            <User size={16} className="text-white" />
          </div>
          <span className="text-sm font-medium">Admin</span>
        </button>
      </div>
    </header>
  );
}
