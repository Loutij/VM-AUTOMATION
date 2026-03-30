import { useEffect, useRef, useCallback } from 'react';
import { Terminal, Wifi, WifiOff, X, RefreshCw } from 'lucide-react';
import { useVMTerminal } from '../../hooks/useVMTerminal';
import { Button } from '../ui';

interface VMTerminalProps {
  vmId: string;
  vmName?: string;
  onClose?: () => void;
}

export function VMTerminal({ vmId, vmName, onClose }: VMTerminalProps) {
  const { status, shellType, sendInput, disconnect, reconnect, outputRef } =
    useVMTerminal({ vmId });

  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-focus on connect
  useEffect(() => {
    if (status === 'connected') {
      const timer = setTimeout(() => containerRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
  }, [status]);

  // Keyboard handler
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (status !== 'connected') return;
      e.preventDefault();
      e.stopPropagation();

      // Map key events to terminal input
      if (e.key === 'Enter') {
        sendInput('\r');
      } else if (e.key === 'Backspace') {
        sendInput('\x7f');
      } else if (e.key === 'Tab') {
        sendInput('\t');
      } else if (e.key === 'Escape') {
        sendInput('\x1b');
      } else if (e.key === 'ArrowUp') {
        sendInput('\x1b[A');
      } else if (e.key === 'ArrowDown') {
        sendInput('\x1b[B');
      } else if (e.key === 'ArrowRight') {
        sendInput('\x1b[C');
      } else if (e.key === 'ArrowLeft') {
        sendInput('\x1b[D');
      } else if (e.key === 'Home') {
        sendInput('\x1b[H');
      } else if (e.key === 'End') {
        sendInput('\x1b[F');
      } else if (e.key === 'Delete') {
        sendInput('\x1b[3~');
      } else if (e.key === 'PageUp') {
        sendInput('\x1b[5~');
      } else if (e.key === 'PageDown') {
        sendInput('\x1b[6~');
      } else if (e.key === 'Insert') {
        sendInput('\x1b[2~');
      } else if (e.ctrlKey && e.key.length === 1) {
        // Ctrl+key combinations
        const code = e.key.toLowerCase().charCodeAt(0) - 96;
        if (code > 0 && code < 27) {
          sendInput(String.fromCharCode(code));
        }
      } else if (e.key.length === 1) {
        sendInput(e.key);
      }
    },
    [sendInput, status],
  );

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

  return (
    <div
      ref={containerRef}
      className="flex flex-col h-full bg-gray-900 outline-none focus:ring-2 focus:ring-green-500 focus:ring-inset"
      tabIndex={0}
      onKeyDown={handleKeyDown}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <Terminal size={18} className="text-green-400" />
          <span className="text-white font-medium text-sm">
            {vmName || vmId} - {shellType === 'ssh' ? 'SSH' : 'PowerShell'}
          </span>
          <div className={`flex items-center gap-1.5 text-xs ${statusColor[status]}`}>
            {status === 'connected' ? <Wifi size={14} /> : <WifiOff size={14} />}
            {statusLabel[status]}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {(status === 'disconnected' || status === 'error') && (
            <Button size="sm" variant="secondary" onClick={reconnect}>
              <RefreshCw size={14} />
            </Button>
          )}
          {onClose && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => { disconnect(); onClose(); }}
            >
              <X size={14} />
            </Button>
          )}
        </div>
      </div>

      {/* Terminal output area */}
      <div
        className="flex-1 overflow-hidden cursor-text"
        onClick={() => containerRef.current?.focus()}
      >
        {status === 'connecting' && (
          <div className="flex items-center justify-center h-full text-gray-400">
            <RefreshCw size={24} className="animate-spin mr-2" />
            <span>Connexion au terminal...</span>
          </div>
        )}
        {status === 'error' && (
          <div className="flex flex-col items-center justify-center h-full text-red-400 gap-2">
            <WifiOff size={24} />
            <span>Erreur de connexion</span>
            <Button size="sm" variant="secondary" onClick={reconnect}>Reconnecter</Button>
          </div>
        )}
        <div
          ref={outputRef}
          className={`h-full overflow-y-auto p-4 font-mono text-sm text-green-300 bg-black whitespace-pre-wrap break-all leading-5 ${
            status !== 'connected' ? 'hidden' : ''
          }`}
          style={{ fontFamily: "'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace" }}
        />
      </div>
    </div>
  );
}
