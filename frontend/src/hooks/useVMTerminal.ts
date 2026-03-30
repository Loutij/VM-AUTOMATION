import { useEffect, useRef, useState, useCallback } from 'react';

export type TerminalStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface UseVMTerminalOptions {
  vmId: string;
  onConnected?: () => void;
  onError?: (error: string) => void;
}

export interface UseVMTerminalReturn {
  status: TerminalStatus;
  shellType: string;
  sendInput: (data: string) => void;
  disconnect: () => void;
  reconnect: () => void;
  outputRef: React.RefObject<HTMLDivElement | null>;
}

export function useVMTerminal(options: UseVMTerminalOptions): UseVMTerminalReturn {
  const { vmId } = options;
  const onConnectedRef = useRef(options.onConnected);
  const onErrorRef = useRef(options.onError);
  onConnectedRef.current = options.onConnected;
  onErrorRef.current = options.onError;

  const [status, setStatus] = useState<TerminalStatus>('disconnected');
  const [shellType, setShellType] = useState<string>('powershell');
  const wsRef = useRef<WebSocket | null>(null);
  const outputRef = useRef<HTMLDivElement | null>(null);
  const mountedRef = useRef(true);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const getWsUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/v1/terminal/ws/${vmId}`;
  }, [vmId]);

  /** Strip PowerShell CLIXML garbage that sometimes leaks through */
  const stripClixml = useCallback((text: string): string => {
    // Remove full CLIXML blocks: #< CLIXML ... </Objs>
    let cleaned = text.replace(/#< CLIXML[\s\S]*?<\/Objs>/g, '');
    // Remove partial CLIXML tags that may appear on their own
    cleaned = cleaned.replace(/<Objs[^>]*>[\s\S]*?<\/Objs>/g, '');
    // Remove lone CLIXML markers
    cleaned = cleaned.replace(/#< CLIXML\s*/g, '');
    // Remove leftover <S S="Error">...</S> style fragments
    cleaned = cleaned.replace(/<S S="[^"]*">([\s\S]*?)<\/S>/g, '$1');
    // Remove stray XML-looking PowerShell tags
    cleaned = cleaned.replace(/<\/?(?:Objs|S|ToString|Props|MS|Obj)[^>]*>/g, '');
    return cleaned;
  }, []);

  const appendOutput = useCallback((rawText: string) => {
    const el = outputRef.current;
    if (!el) return;

    // Safety-net: strip any CLIXML that the backend didn't catch
    const text = stripClixml(rawText);
    if (!text) return; // nothing left after stripping

    // Convert ANSI escape codes minimally and append
    const span = document.createElement('span');

    // Strip remaining ANSI sequences we don't colorize
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\x1b\[31m/g, '<span style="color:#f87171">')
      .replace(/\x1b\[32m/g, '<span style="color:#4ade80">')
      .replace(/\x1b\[33m/g, '<span style="color:#facc15">')
      .replace(/\x1b\[34m/g, '<span style="color:#60a5fa">')
      .replace(/\x1b\[35m/g, '<span style="color:#c084fc">')
      .replace(/\x1b\[36m/g, '<span style="color:#22d3ee">')
      .replace(/\x1b\[1m/g, '<span style="font-weight:bold">')
      .replace(/\x1b\[0m/g, '</span>')
      .replace(/\x1b\[2J\x1b\[H/g, '') // clear screen handled separately
      .replace(/\x1b\[[0-9;]*[A-Za-z]/g, ''); // strip any remaining unhandled ANSI sequences

    // Handle clear screen
    if (text.includes('\x1b[2J')) {
      el.innerHTML = '';
    }

    // Handle backspace
    if (html.includes('\b')) {
      const parts = html.split('\b');
      for (let i = 0; i < parts.length; i++) {
        if (i > 0) {
          // Each \b removes last character
          const lastChild = el.lastChild;
          if (lastChild && lastChild.textContent) {
            lastChild.textContent = lastChild.textContent.slice(0, -1);
            if (!lastChild.textContent) {
              el.removeChild(lastChild);
            }
          }
        }
        if (parts[i]) {
          const s = document.createElement('span');
          s.innerHTML = parts[i];
          el.appendChild(s);
        }
      }
    } else {
      span.innerHTML = html;
      el.appendChild(span);
    }

    // Always auto-scroll to bottom
    el.scrollTop = el.scrollHeight;
  }, [stripClixml]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) return;

    setStatus('connecting');

    try {
      // Append auth token to WebSocket URL for server-side verification
      const token = localStorage.getItem('access_token');
      const baseUrl = getWsUrl();
      const separator = baseUrl.includes('?') ? '&' : '?';
      const wsUrl = token ? `${baseUrl}${separator}token=${encodeURIComponent(token)}` : baseUrl;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        if (!mountedRef.current || wsRef.current !== ws) return;

        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'connected') {
            setStatus('connected');
            setShellType(msg.shell || 'powershell');
            reconnectAttemptsRef.current = 0;
            onConnectedRef.current?.();
          } else if (msg.type === 'output') {
            appendOutput(msg.data || '');
          } else if (msg.type === 'error') {
            setStatus('error');
            onErrorRef.current?.(msg.message || 'Terminal error');
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current || wsRef.current !== ws) return;
        setStatus('disconnected');
        wsRef.current = null;

        if (mountedRef.current && reconnectAttemptsRef.current < 5) {
          reconnectAttemptsRef.current++;
          const delay = Math.min(1000 * reconnectAttemptsRef.current, 5000);
          reconnectTimeoutRef.current = setTimeout(() => {
            if (mountedRef.current) connect();
          }, delay);
        }
      };

      ws.onerror = () => {
        if (!mountedRef.current || wsRef.current !== ws) return;
        setStatus('error');
      };
    } catch {
      setStatus('error');
    }
  }, [getWsUrl, appendOutput]);

  const disconnect = useCallback(() => {
    reconnectAttemptsRef.current = 5;
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    reconnectAttemptsRef.current = 0;
    // Clear terminal
    if (outputRef.current) outputRef.current.innerHTML = '';
    setTimeout(() => connect(), 100);
  }, [disconnect, connect]);

  const sendInput = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'input', data }));
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const timer = setTimeout(() => {
      if (mountedRef.current) connect();
    }, 150);
    return () => {
      mountedRef.current = false;
      clearTimeout(timer);
      reconnectAttemptsRef.current = 5;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { status, shellType, sendInput, disconnect, reconnect, outputRef };
}
