import { useState, useCallback, useRef } from 'react';
import {
  Monitor,
  Wifi,
  WifiOff,
  Maximize,
  Minimize,
  X,
  RefreshCw,
  Keyboard,
  Eye,
  EyeOff,
  Scaling,
  Clipboard,
} from 'lucide-react';
import { useVNC } from '../../hooks/useVNC';
import { Button } from '../ui';

interface VNCViewerProps {
  vmId: string;
  vmName?: string;
  onClose?: () => void;
}

export function VNCViewer({ vmId, vmName, onClose }: VNCViewerProps) {
  const [isViewOnly, setIsViewOnly] = useState(false);
  const [isScaled, setIsScaled] = useState(true);
  const [showClipboard, setShowClipboard] = useState(false);
  const clipboardRef = useRef<HTMLTextAreaElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const {
    containerRef,
    state,
    connect,
    disconnect,
    sendCtrlAltDel,
    setViewOnly,
    setScaleViewport,
    sendClipboard,
  } = useVNC({
    vmId,
    viewOnly: isViewOnly,
    scaleViewport: isScaled,
  });

  // ---------------------------------------------------------------------------
  // Toggles
  // ---------------------------------------------------------------------------

  const toggleViewOnly = useCallback(() => {
    const next = !isViewOnly;
    setIsViewOnly(next);
    setViewOnly(next);
  }, [isViewOnly, setViewOnly]);

  const toggleScale = useCallback(() => {
    const next = !isScaled;
    setIsScaled(next);
    setScaleViewport(next);
  }, [isScaled, setScaleViewport]);

  // ---------------------------------------------------------------------------
  // Clipboard paste
  // ---------------------------------------------------------------------------

  const handlePasteClipboard = useCallback(() => {
    const text = clipboardRef.current?.value;
    if (text) {
      sendClipboard(text);
      setShowClipboard(false);
    }
  }, [sendClipboard]);

  // ---------------------------------------------------------------------------
  // Fullscreen
  // ---------------------------------------------------------------------------

  const toggleFullscreen = useCallback(() => {
    if (!wrapperRef.current) return;
    if (!document.fullscreenElement) {
      wrapperRef.current.requestFullscreen();
    } else {
      document.exitFullscreen();
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Status helpers
  // ---------------------------------------------------------------------------

  const statusDotColor: Record<string, string> = {
    connecting: 'bg-yellow-400',
    connected: 'bg-green-400',
    disconnected: 'bg-gray-400',
    error: 'bg-red-400',
  };

  const statusLabel: Record<string, string> = {
    connecting: 'Connexion...',
    connected: 'Connecte',
    disconnected: 'Deconnecte',
    error: 'Erreur',
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div ref={wrapperRef} className="flex flex-col h-full bg-gray-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <Monitor size={18} className="text-gray-400" />
          <span className="text-white font-medium text-sm">
            {vmName || vmId}
          </span>
          <div className="flex items-center gap-1.5 text-xs text-gray-300">
            <span className={`inline-block w-2 h-2 rounded-full ${statusDotColor[state.status]}`} />
            {statusLabel[state.status]}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Ctrl+Alt+Del */}
          <Button
            size="sm"
            variant="secondary"
            onMouseDown={(e: React.MouseEvent) => e.preventDefault()}
            onClick={sendCtrlAltDel}
            disabled={state.status !== 'connected'}
            title="Ctrl+Alt+Del"
          >
            <Keyboard size={14} />
            <span className="text-xs hidden sm:inline">Ctrl+Alt+Del</span>
          </Button>

          {/* View Only toggle */}
          <Button
            size="sm"
            variant="secondary"
            onMouseDown={(e: React.MouseEvent) => e.preventDefault()}
            onClick={toggleViewOnly}
            disabled={state.status !== 'connected'}
            title={isViewOnly ? 'Mode interactif' : 'Mode lecture seule'}
          >
            {isViewOnly ? <EyeOff size={14} /> : <Eye size={14} />}
          </Button>

          {/* Scale toggle */}
          <Button
            size="sm"
            variant="secondary"
            onMouseDown={(e: React.MouseEvent) => e.preventDefault()}
            onClick={toggleScale}
            disabled={state.status !== 'connected'}
            title={isScaled ? 'Taille reelle' : 'Ajuster a la fenetre'}
          >
            <Scaling size={14} />
          </Button>

          {/* Clipboard */}
          <Button
            size="sm"
            variant="secondary"
            onMouseDown={(e: React.MouseEvent) => e.preventDefault()}
            onClick={() => setShowClipboard(!showClipboard)}
            disabled={state.status !== 'connected'}
            title="Presse-papiers"
          >
            <Clipboard size={14} />
          </Button>

          {/* Fullscreen */}
          <Button
            size="sm"
            variant="secondary"
            onMouseDown={(e: React.MouseEvent) => e.preventDefault()}
            onClick={toggleFullscreen}
          >
            {document.fullscreenElement ? <Minimize size={14} /> : <Maximize size={14} />}
          </Button>

          {/* Reconnect / Disconnect */}
          {(state.status === 'disconnected' || state.status === 'error') ? (
            <Button size="sm" variant="secondary" onClick={connect}>
              <RefreshCw size={14} />
              <span className="text-xs hidden sm:inline">Reconnecter</span>
            </Button>
          ) : state.status === 'connected' ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                disconnect();
                if (onClose) onClose();
              }}
            >
              {onClose ? <X size={14} /> : <WifiOff size={14} />}
            </Button>
          ) : null}

          {/* Close (if no disconnect+close combo) */}
          {onClose && state.status === 'connected' && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                disconnect();
                onClose();
              }}
            >
              <X size={14} />
            </Button>
          )}
        </div>
      </div>

      {/* Clipboard panel */}
      {showClipboard && (
        <div className="px-4 py-2 bg-gray-800 border-b border-gray-700 flex items-center gap-2">
          <textarea
            ref={clipboardRef}
            className="flex-1 bg-gray-900 text-gray-200 text-sm rounded px-3 py-1.5 border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none resize-none"
            rows={2}
            placeholder="Texte a envoyer au presse-papiers de la VM..."
          />
          <Button size="sm" variant="primary" onClick={handlePasteClipboard}>
            Envoyer
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setShowClipboard(false)}>
            <X size={14} />
          </Button>
        </div>
      )}

      {/* noVNC canvas area */}
      <div className="flex-1 flex items-center justify-center overflow-hidden bg-black relative">
        {state.status === 'connecting' && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="text-gray-400 flex flex-col items-center gap-2">
              <RefreshCw size={24} className="animate-spin" />
              <span>Connexion VNC en cours...</span>
            </div>
          </div>
        )}

        {state.status === 'error' && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="text-red-400 flex flex-col items-center gap-3">
              <WifiOff size={24} />
              <span>{state.error || 'Erreur de connexion'}</span>
              <Button size="sm" variant="secondary" onClick={connect}>
                <RefreshCw size={14} className="mr-1" />
                Reconnecter
              </Button>
            </div>
          </div>
        )}

        {state.status === 'disconnected' && !state.error && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="text-gray-400 flex flex-col items-center gap-3">
              <Wifi size={24} />
              <span>Deconnecte</span>
              <Button size="sm" variant="secondary" onClick={connect}>
                <RefreshCw size={14} className="mr-1" />
                Connecter
              </Button>
            </div>
          </div>
        )}

        {/* noVNC mounts its canvas inside this div */}
        <div
          ref={containerRef}
          className="w-full h-full"
          style={{ display: state.status === 'connected' || state.status === 'connecting' ? 'block' : 'none' }}
        />
      </div>
    </div>
  );
}
