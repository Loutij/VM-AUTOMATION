import { useEffect, useRef, useState, useCallback } from 'react';

export type ConsoleStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface UseVMConsoleOptions {
  vmId: string;
  onConnected?: () => void;
  onError?: (error: string) => void;
  onDisconnected?: () => void;
}

export interface UseVMConsoleReturn {
  status: ConsoleStatus;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  sendKey: (scancode: number, action: 'type' | 'press' | 'release') => void;
  sendText: (text: string) => void;
  sendMouseClick: (x: number, y: number, button: number) => void;
  sendMouseMove: (x: number, y: number) => void;
  disconnect: () => void;
  reconnect: () => void;
  fps: number;
}

export function useVMConsole(options: UseVMConsoleOptions): UseVMConsoleReturn {
  const { vmId } = options;

  // Store callbacks in refs to avoid recreating connect on every render
  const onConnectedRef = useRef(options.onConnected);
  const onErrorRef = useRef(options.onError);
  const onDisconnectedRef = useRef(options.onDisconnected);
  onConnectedRef.current = options.onConnected;
  onErrorRef.current = options.onError;
  onDisconnectedRef.current = options.onDisconnected;

  const [status, setStatus] = useState<ConsoleStatus>('disconnected');
  const [fps, setFps] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const frameCountRef = useRef(0);
  const fpsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const mountedRef = useRef(true);
  const maxReconnectAttempts = 5;

  const getWsUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/v1/console/ws/${vmId}`;
  }, [vmId]);

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
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        // Wait for server "connected" message before setting status
      };

      ws.onmessage = async (event) => {
        // Ignore events from stale WS (StrictMode double-invoke)
        if (!mountedRef.current || wsRef.current !== ws) return;

        if (event.data instanceof ArrayBuffer) {
          // Binary frame: PNG screenshot
          frameCountRef.current++;
          const blob = new Blob([event.data], { type: 'image/png' });
          try {
            const bitmap = await createImageBitmap(blob);
            const canvas = canvasRef.current;
            if (canvas) {
              if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
                canvas.width = bitmap.width;
                canvas.height = bitmap.height;
              }
              const ctx = canvas.getContext('2d');
              if (ctx) {
                ctx.drawImage(bitmap, 0, 0);
              }
            }
            bitmap.close();
          } catch {
            // Ignore frame decode errors
          }
        } else if (typeof event.data === 'string') {
          // Text frame: JSON control message
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'connected') {
              setStatus('connected');
              reconnectAttemptsRef.current = 0;
              onConnectedRef.current?.();
            } else if (msg.type === 'error') {
              setStatus('error');
              onErrorRef.current?.(msg.message || 'Console error');
            }
          } catch {
            // Ignore parse errors
          }
        }
      };

      ws.onclose = () => {
        // Ignore close events from stale WS (StrictMode double-invoke)
        if (!mountedRef.current || wsRef.current !== ws) return;
        setStatus('disconnected');
        wsRef.current = null;
        onDisconnectedRef.current?.();

        // Auto-reconnect with exponential backoff
        if (mountedRef.current && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          const delay = Math.min(1000 * reconnectAttemptsRef.current, 5000);
          reconnectTimeoutRef.current = setTimeout(() => {
            if (mountedRef.current) connect();
          }, delay);
        }
      };

      ws.onerror = () => {
        // Ignore error events from stale WS (StrictMode double-invoke)
        if (!mountedRef.current || wsRef.current !== ws) return;
        setStatus('error');
      };
    } catch {
      setStatus('error');
    }
  }, [getWsUrl]); // Only depends on getWsUrl (stable per vmId)

  const disconnect = useCallback(() => {
    reconnectAttemptsRef.current = maxReconnectAttempts; // Prevent auto-reconnect
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
    setTimeout(() => connect(), 100);
  }, [disconnect, connect]);

  const sendKey = useCallback((scancode: number, action: 'type' | 'press' | 'release') => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'key',
        scancode,
        action,
      }));
    }
  }, []);

  const sendText = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'text',
        value: text,
      }));
    }
  }, []);

  const sendMouseClick = useCallback((x: number, y: number, button: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'mouse_click',
        x,
        y,
        button,
      }));
    }
  }, []);

  const sendMouseMove = useCallback((x: number, y: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'mouse_move',
        x,
        y,
      }));
    }
  }, []);

  // FPS counter
  useEffect(() => {
    fpsIntervalRef.current = setInterval(() => {
      setFps(frameCountRef.current);
      frameCountRef.current = 0;
    }, 1000);
    return () => {
      if (fpsIntervalRef.current) clearInterval(fpsIntervalRef.current);
    };
  }, []);

  // Connect on mount, disconnect on unmount
  // Delay initial connect to survive React StrictMode double-invoke:
  // StrictMode runs effect → cleanup → effect. Without delay, the first WS
  // would lock the server-side session and the second WS gets rejected.
  useEffect(() => {
    mountedRef.current = true;
    const timer = setTimeout(() => {
      if (mountedRef.current) connect();
    }, 150);
    return () => {
      mountedRef.current = false;
      clearTimeout(timer);
      reconnectAttemptsRef.current = maxReconnectAttempts;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on cleanup
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    status,
    canvasRef,
    sendKey,
    sendText,
    sendMouseClick,
    sendMouseMove,
    disconnect,
    reconnect,
    fps,
  };
}
