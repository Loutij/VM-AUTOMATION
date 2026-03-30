import { useEffect, useRef, useCallback } from 'react';
import {
  Monitor,
  Wifi,
  WifiOff,
  Maximize,
  X,
  RefreshCw,
  Keyboard,
} from 'lucide-react';
import { useVMConsole } from '../../hooks/useVMConsole';
import { getScancode, isModifierKey } from '../../utils/scancodes';
import { Button } from '../ui';

interface VMConsoleProps {
  vmId: string;
  vmName?: string;
  onClose?: () => void;
}

export function VMConsole({ vmId, vmName, onClose }: VMConsoleProps) {
  const { status, canvasRef, sendKey, sendText, sendMouseClick, sendMouseMove, disconnect, reconnect, fps } =
    useVMConsole({ vmId });

  const containerRef = useRef<HTMLDivElement>(null);
  const lastMouseMoveRef = useRef<number>(0);

  // ---------------------------------------------------------------------------
  // Focus management
  // ---------------------------------------------------------------------------

  const focusContainer = useCallback(() => {
    containerRef.current?.focus();
  }, []);

  // Auto-focus when connected
  useEffect(() => {
    if (status === 'connected') {
      // Small delay to ensure the canvas is visible before focusing
      const timer = setTimeout(focusContainer, 50);
      return () => clearTimeout(timer);
    }
  }, [status, focusContainer]);

  // ---------------------------------------------------------------------------
  // Keyboard handling
  // ---------------------------------------------------------------------------

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      // Ignore auto-repeat for modifier keys (browser fires repeated keydown
      // while a key is held, but we only need a single press for modifiers)
      if (e.repeat && isModifierKey(e.code)) {
        return;
      }

      // Printable single character -> send as text (more reliable for
      // characters that depend on keyboard layout, e.g. shifted symbols)
      if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        sendText(e.key);
        return;
      }

      const scancode = getScancode(e.code);
      if (scancode !== null) {
        if (isModifierKey(e.code)) {
          sendKey(scancode, 'press');
        } else {
          sendKey(scancode, 'type');
        }
      }
    },
    [sendKey, sendText],
  );

  const handleKeyUp = useCallback(
    (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      // Only release modifiers on keyup
      if (isModifierKey(e.code)) {
        const scancode = getScancode(e.code);
        if (scancode !== null) {
          sendKey(scancode, 'release');
        }
      }
    },
    [sendKey],
  );

  // Attach keyboard handlers to container
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.addEventListener('keydown', handleKeyDown);
    container.addEventListener('keyup', handleKeyUp);

    return () => {
      container.removeEventListener('keydown', handleKeyDown);
      container.removeEventListener('keyup', handleKeyUp);
    };
  }, [handleKeyDown, handleKeyUp]);

  // ---------------------------------------------------------------------------
  // Mouse click handling
  // ---------------------------------------------------------------------------

  const handleCanvasMouseClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas || status !== 'connected') return;

      const rect = canvas.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      sendMouseClick(x, y, 1);
    },
    [canvasRef, sendMouseClick, status],
  );

  const handleCanvasContextMenu = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      const canvas = canvasRef.current;
      if (!canvas || status !== 'connected') return;

      const rect = canvas.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      sendMouseClick(x, y, 2);
    },
    [canvasRef, sendMouseClick, status],
  );

  // ---------------------------------------------------------------------------
  // Mouse move handling (throttled to max 10/s)
  // ---------------------------------------------------------------------------

  const handleCanvasMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const now = performance.now();
      if (now - lastMouseMoveRef.current < 100) return; // 100ms = 10/s
      lastMouseMoveRef.current = now;

      const canvas = canvasRef.current;
      if (!canvas || status !== 'connected') return;

      const rect = canvas.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      sendMouseMove(x, y);
    },
    [canvasRef, sendMouseMove, status],
  );

  // ---------------------------------------------------------------------------
  // Special key combos
  // ---------------------------------------------------------------------------

  const sendCtrlAltDel = useCallback(() => {
    const ctrlScancode = getScancode('ControlLeft')!;
    const altScancode = getScancode('AltLeft')!;
    const delScancode = getScancode('Delete')!;

    sendKey(ctrlScancode, 'press');
    sendKey(altScancode, 'press');
    sendKey(delScancode, 'type');
    sendKey(altScancode, 'release');
    sendKey(ctrlScancode, 'release');
  }, [sendKey]);

  // ---------------------------------------------------------------------------
  // Fullscreen
  // ---------------------------------------------------------------------------

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen();
    } else {
      document.exitFullscreen();
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Status helpers
  // ---------------------------------------------------------------------------

  const statusColor: Record<string, string> = {
    connecting: 'text-yellow-400',
    connected: 'text-green-400',
    disconnected: 'text-gray-400',
    error: 'text-red-400',
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
    <div
      ref={containerRef}
      className="flex flex-col h-full bg-gray-900 outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset"
      tabIndex={0}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <Monitor size={18} className="text-gray-400" />
          <span className="text-white font-medium text-sm">
            {vmName || vmId}
          </span>
          <div
            className={`flex items-center gap-1.5 text-xs ${statusColor[status]}`}
          >
            {status === 'connected' ? (
              <Wifi size={14} />
            ) : (
              <WifiOff size={14} />
            )}
            {statusLabel[status]}
          </div>
          {status === 'connected' && (
            <span className="text-xs text-gray-500">{fps} FPS</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onMouseDown={(e: React.MouseEvent) => e.preventDefault()}
            onClick={() => { sendCtrlAltDel(); focusContainer(); }}
            disabled={status !== 'connected'}
            title="Ctrl+Alt+Del"
          >
            <Keyboard size={14} />
            <span className="text-xs">Ctrl+Alt+Del</span>
          </Button>

          {(status === 'disconnected' || status === 'error') && (
            <Button size="sm" variant="secondary" onClick={reconnect}>
              <RefreshCw size={14} />
            </Button>
          )}

          <Button
            size="sm"
            variant="secondary"
            onMouseDown={(e: React.MouseEvent) => e.preventDefault()}
            onClick={() => { toggleFullscreen(); focusContainer(); }}
          >
            <Maximize size={14} />
          </Button>

          {onClose && (
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

      {/* Canvas area -- clicking anywhere here focuses the container for keyboard input */}
      <div
        className="flex-1 flex items-center justify-center overflow-hidden bg-black cursor-default"
        onClick={focusContainer}
      >
        {status === 'connecting' && (
          <div className="text-gray-400 flex flex-col items-center gap-2">
            <RefreshCw size={24} className="animate-spin" />
            <span>Connexion a la console...</span>
          </div>
        )}
        {status === 'error' && (
          <div className="text-red-400 flex flex-col items-center gap-2">
            <WifiOff size={24} />
            <span>Erreur de connexion</span>
            <Button size="sm" variant="secondary" onClick={reconnect}>
              Reconnecter
            </Button>
          </div>
        )}
        <canvas
          ref={canvasRef}
          className={`max-w-full max-h-full object-contain ${
            status !== 'connected' ? 'hidden' : ''
          }`}
          style={{ imageRendering: 'auto', cursor: status === 'connected' ? 'crosshair' : 'default' }}
          onClick={handleCanvasMouseClick}
          onContextMenu={handleCanvasContextMenu}
          onMouseMove={handleCanvasMouseMove}
        />
      </div>
    </div>
  );
}
