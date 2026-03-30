import React, { useState, useCallback } from 'react';

interface VNCToolbarProps {
  status: 'disconnected' | 'connecting' | 'connected' | 'error';
  vmName: string;
  onConnect: () => void;
  onDisconnect: () => void;
  onCtrlAltDel: () => void;
  onToggleViewOnly: (value: boolean) => void;
  onToggleScale: (value: boolean) => void;
  onSendClipboard: (text: string) => void;
  onBack: () => void;
}

export function VNCToolbar({
  status,
  vmName,
  onConnect,
  onDisconnect,
  onCtrlAltDel,
  onToggleViewOnly,
  onToggleScale,
  onSendClipboard,
  onBack,
}: VNCToolbarProps) {
  const [isViewOnly, setIsViewOnly] = useState(false);
  const [isScaled, setIsScaled] = useState(true);
  const [showClipboard, setShowClipboard] = useState(false);
  const [clipboardText, setClipboardText] = useState('');
  const isConnected = status === 'connected';

  // ---------------------------------------------------------------------------
  // Fullscreen
  // ---------------------------------------------------------------------------

  const handleFullscreen = useCallback(() => {
    const el = document.getElementById('vnc-container');
    if (el) {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        el.requestFullscreen();
      }
    }
  }, []);

  // ---------------------------------------------------------------------------
  // View-only toggle
  // ---------------------------------------------------------------------------

  const handleViewOnly = useCallback(() => {
    const newValue = !isViewOnly;
    setIsViewOnly(newValue);
    onToggleViewOnly(newValue);
  }, [isViewOnly, onToggleViewOnly]);

  // ---------------------------------------------------------------------------
  // Scale toggle
  // ---------------------------------------------------------------------------

  const handleScale = useCallback(() => {
    const newValue = !isScaled;
    setIsScaled(newValue);
    onToggleScale(newValue);
  }, [isScaled, onToggleScale]);

  // ---------------------------------------------------------------------------
  // Clipboard
  // ---------------------------------------------------------------------------

  const handlePasteClipboard = useCallback(() => {
    if (clipboardText) {
      onSendClipboard(clipboardText);
      setClipboardText('');
      setShowClipboard(false);
    }
  }, [clipboardText, onSendClipboard]);

  // ---------------------------------------------------------------------------
  // Status helpers
  // ---------------------------------------------------------------------------

  const statusColors = {
    disconnected: 'bg-gray-400',
    connecting: 'bg-yellow-400 animate-pulse',
    connected: 'bg-green-500',
    error: 'bg-red-500',
  };

  const statusLabels = {
    disconnected: 'Deconnecte',
    connecting: 'Connexion...',
    connected: 'Connecte',
    error: 'Erreur',
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="bg-white dark:bg-dark-800 border-b border-gray-200 dark:border-dark-700 px-4 py-2">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            title="Retour"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>

          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${statusColors[status]}`} />
            <span className="font-medium text-gray-900 dark:text-white text-sm">
              {vmName || 'VM'} — VNC
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              ({statusLabels[status]})
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {/* Connect/Disconnect */}
          {isConnected ? (
            <ToolbarButton onClick={onDisconnect} title="Deconnecter" variant="danger">
              <PowerIcon />
            </ToolbarButton>
          ) : (
            <ToolbarButton onClick={onConnect} title="Connecter" variant="primary" disabled={status === 'connecting'}>
              <PlayIcon />
            </ToolbarButton>
          )}

          <div className="w-px h-6 bg-gray-300 dark:bg-dark-600 mx-1" />

          {/* Ctrl+Alt+Del */}
          <ToolbarButton onClick={onCtrlAltDel} title="Ctrl+Alt+Suppr" disabled={!isConnected}>
            <span className="text-xs font-mono">C+A+D</span>
          </ToolbarButton>

          {/* View Only */}
          <ToolbarButton onClick={handleViewOnly} title={isViewOnly ? 'Mode interactif' : 'Mode lecture seule'} active={isViewOnly} disabled={!isConnected}>
            <EyeIcon />
          </ToolbarButton>

          {/* Scale */}
          <ToolbarButton onClick={handleScale} title={isScaled ? 'Taille reelle' : 'Adapter a la fenetre'} active={isScaled} disabled={!isConnected}>
            <ScaleIcon />
          </ToolbarButton>

          {/* Clipboard */}
          <ToolbarButton onClick={() => setShowClipboard(!showClipboard)} title="Presse-papiers" active={showClipboard} disabled={!isConnected}>
            <ClipboardIcon />
          </ToolbarButton>

          {/* Fullscreen */}
          <ToolbarButton onClick={handleFullscreen} title="Plein ecran" disabled={!isConnected}>
            <FullscreenIcon />
          </ToolbarButton>
        </div>
      </div>

      {/* Clipboard panel */}
      {showClipboard && (
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={clipboardText}
            onChange={e => setClipboardText(e.target.value)}
            placeholder="Texte a envoyer..."
            className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-dark-600 rounded-lg bg-white dark:bg-dark-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            onKeyDown={e => e.key === 'Enter' && handlePasteClipboard()}
          />
          <button
            onClick={handlePasteClipboard}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Envoyer
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ToolbarButton({ children, onClick, title, disabled, active, variant }: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  disabled?: boolean;
  active?: boolean;
  variant?: 'primary' | 'danger';
}) {
  const baseClasses = 'p-1.5 rounded-md text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed';
  const variantClasses = variant === 'danger'
    ? 'text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20'
    : variant === 'primary'
    ? 'text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/20'
    : active
    ? 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20'
    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-dark-700';

  return (
    <button onClick={onClick} title={title} disabled={disabled} className={`${baseClasses} ${variantClasses}`}>
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Icons (inline SVGs)
// ---------------------------------------------------------------------------

function PowerIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 11-12.728 0M12 3v9" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  );
}

function ScaleIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
    </svg>
  );
}

function ClipboardIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
    </svg>
  );
}

function FullscreenIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-5h-4m4 0v4m0-4l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5h-4m4 0v-4m0 4l-5-5" />
    </svg>
  );
}
