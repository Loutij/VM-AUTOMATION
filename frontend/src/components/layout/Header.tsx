import { useState, useRef, useEffect, useCallback } from 'react';
import { Bell, Search, User, LogOut, ChevronDown, CheckCircle, XCircle, AlertTriangle, Info, Trash2, Check } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useNotifications, type NotificationPayload } from '../../hooks/useWebSocket';
import { useToast } from '../ui/Toast';

interface HeaderProps {
  title: string;
}

// Icônes par type de notification
const notificationIcons: Record<NotificationPayload['type'], typeof CheckCircle> = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const notificationColors: Record<NotificationPayload['type'], string> = {
  success: 'text-green-500',
  error: 'text-red-500',
  warning: 'text-yellow-500',
  info: 'text-blue-500',
};

export function Header({ title }: HeaderProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [localNotifications, setLocalNotifications] = useState<NotificationPayload[]>([]);
  const [readNotifications, setReadNotifications] = useState<Set<string>>(new Set());
  const menuRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  // Callback pour nouvelles notifications temps réel
  const handleNewNotification = useCallback((notification: NotificationPayload) => {
    // Ajouter à la liste locale
    setLocalNotifications(prev => [notification, ...prev].slice(0, 50));
    
    // Afficher un toast pour les notifications importantes
    if (notification.type === 'error' || notification.type === 'success') {
      addToast({
        type: notification.type,
        title: notification.title,
        message: notification.message,
      });
    }
  }, [addToast]);

  // Hook WebSocket pour les notifications
  const { notifications: wsNotifications, isConnected, clearNotifications } = useNotifications(handleNewNotification);

  // Combiner notifications WebSocket et locales (éviter les doublons)
  const allNotifications = [...localNotifications];
  wsNotifications.forEach(n => {
    if (!allNotifications.find(ln => ln.id === n.id)) {
      allNotifications.push(n);
    }
  });
  // Trier par ID (supposé être chronologique)
  allNotifications.sort((a, b) => b.id.localeCompare(a.id));

  // Nombre de notifications non lues
  const unreadCount = allNotifications.filter(n => !readNotifications.has(n.id)).length;

  // Fermer les menus au clic extérieur
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Marquer toutes comme lues
  const markAllAsRead = () => {
    const allIds = new Set(allNotifications.map(n => n.id));
    setReadNotifications(allIds);
  };

  // Supprimer une notification
  const removeNotification = (id: string) => {
    setLocalNotifications(prev => prev.filter(n => n.id !== id));
  };

  // Tout effacer
  const clearAll = () => {
    setLocalNotifications([]);
    clearNotifications();
    setReadNotifications(new Set());
  };

  // Formater l'heure basé sur l'ID (qui contient un timestamp)
  const formatTime = (id: string) => {
    // Essayer d'extraire un timestamp de l'ID
    const timestamp = parseInt(id.split('-')[0], 10);
    if (!isNaN(timestamp) && timestamp > 0) {
      const diff = Date.now() - timestamp;
      const minutes = Math.floor(diff / 60000);
      if (minutes < 1) return "À l'instant";
      if (minutes < 60) return `Il y a ${minutes} min`;
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return `Il y a ${hours}h`;
      return `Il y a ${Math.floor(hours / 24)}j`;
    }
    return "À l'instant";
  };

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
        <div className="relative" ref={notifRef}>
          <button 
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 text-dark-300 hover:text-white hover:bg-dark-700 rounded-lg transition-colors"
            title={isConnected ? 'Notifications (connecté)' : 'Notifications (déconnecté)'}
          >
            <Bell size={20} />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-primary-500 rounded-full text-xs font-medium text-white flex items-center justify-center">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
            {!isConnected && (
              <span className="absolute bottom-0 right-0 w-2 h-2 bg-yellow-500 rounded-full border border-dark-800" title="Déconnecté" />
            )}
          </button>

          {/* Panneau des notifications */}
          {showNotifications && (
            <div className="absolute right-0 top-full mt-2 w-96 bg-dark-700 border border-dark-600 rounded-lg shadow-xl z-50 overflow-hidden">
              {/* Header du panneau */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-dark-600">
                <h3 className="font-medium text-white">Notifications</h3>
                <div className="flex items-center gap-2">
                  {unreadCount > 0 && (
                    <button
                      onClick={markAllAsRead}
                      className="p-1 text-dark-400 hover:text-primary-400 transition-colors"
                      title="Tout marquer comme lu"
                    >
                      <Check size={16} />
                    </button>
                  )}
                  {allNotifications.length > 0 && (
                    <button
                      onClick={clearAll}
                      className="p-1 text-dark-400 hover:text-red-400 transition-colors"
                      title="Tout effacer"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              </div>

              {/* Liste des notifications */}
              <div className="max-h-96 overflow-y-auto">
                {allNotifications.length === 0 ? (
                  <div className="px-4 py-8 text-center">
                    <Bell size={32} className="mx-auto text-dark-500 mb-2" />
                    <p className="text-dark-400 text-sm">Aucune notification</p>
                    <p className="text-dark-500 text-xs mt-1">
                      {isConnected ? 'Les nouvelles notifications apparaîtront ici' : 'Connexion en cours...'}
                    </p>
                  </div>
                ) : (
                  allNotifications.map((notification) => {
                    const Icon = notificationIcons[notification.type];
                    const colorClass = notificationColors[notification.type];
                    const isRead = readNotifications.has(notification.id);
                    
                    return (
                      <div
                        key={notification.id}
                        className={`px-4 py-3 border-b border-dark-600 last:border-b-0 hover:bg-dark-600/50 transition-colors ${
                          !isRead ? 'bg-dark-600/30' : ''
                        }`}
                        onClick={() => setReadNotifications(prev => new Set([...prev, notification.id]))}
                      >
                        <div className="flex items-start gap-3">
                          <Icon size={18} className={`flex-shrink-0 mt-0.5 ${colorClass}`} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between">
                              <p className={`text-sm font-medium ${!isRead ? 'text-white' : 'text-dark-200'}`}>
                                {notification.title}
                              </p>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  removeNotification(notification.id);
                                }}
                                className="p-1 text-dark-500 hover:text-dark-300 transition-colors"
                              >
                                <XCircle size={14} />
                              </button>
                            </div>
                            <p className="text-xs text-dark-400 mt-0.5 line-clamp-2">
                              {notification.message}
                            </p>
                            <p className="text-xs text-dark-500 mt-1">
                              {formatTime(notification.id)}
                            </p>
                          </div>
                          {!isRead && (
                            <span className="w-2 h-2 bg-primary-500 rounded-full flex-shrink-0 mt-2" />
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Footer */}
              {allNotifications.length > 0 && (
                <div className="px-4 py-2 border-t border-dark-600 bg-dark-750">
                  <p className="text-xs text-dark-400 text-center">
                    {allNotifications.length} notification{allNotifications.length > 1 ? 's' : ''}
                    {unreadCount > 0 && ` (${unreadCount} non lue${unreadCount > 1 ? 's' : ''})`}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* User menu */}
        <div className="relative" ref={menuRef}>
          <button 
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 p-2 text-dark-300 hover:text-white hover:bg-dark-700 rounded-lg transition-colors"
          >
            <div className="w-8 h-8 bg-primary-600 rounded-full flex items-center justify-center">
              <User size={16} className="text-white" />
            </div>
            <span className="text-sm font-medium">{user?.username || 'Utilisateur'}</span>
            <ChevronDown size={16} className={`transition-transform ${showUserMenu ? 'rotate-180' : ''}`} />
          </button>

          {/* Dropdown menu */}
          {showUserMenu && (
            <div className="absolute right-0 top-full mt-2 w-56 bg-dark-700 border border-dark-600 rounded-lg shadow-xl py-2 z-50">
              <div className="px-4 py-2 border-b border-dark-600">
                <p className="text-sm font-medium text-white">{user?.username}</p>
                <p className="text-xs text-dark-400">{user?.email}</p>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-3 px-4 py-2 text-sm text-dark-300 hover:text-white hover:bg-dark-600 transition-colors"
              >
                <LogOut size={16} />
                Se déconnecter
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
