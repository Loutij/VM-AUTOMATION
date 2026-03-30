import { useRef, useState, useCallback, useEffect } from 'react';

interface UseVNCOptions {
  vmId: string;
  autoConnect?: boolean;
  viewOnly?: boolean;
  scaleViewport?: boolean;
  clipViewport?: boolean;
  showDotCursor?: boolean;
  qualityLevel?: number;
  compressionLevel?: number;
}

interface VNCState {
  status: 'disconnected' | 'connecting' | 'connected' | 'error';
  error: string | null;
  vmName: string | null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RFBInstance = any;

export function useVNC(options: UseVNCOptions) {
  const {
    vmId,
    autoConnect = true,
    viewOnly = false,
    scaleViewport = true,
    clipViewport = false,
    showDotCursor = true,
    qualityLevel = 6,
    compressionLevel = 2,
  } = options;

  const rfbRef = useRef<RFBInstance | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<VNCState>({
    status: 'disconnected',
    error: null,
    vmName: null,
  });

  const connect = useCallback(async () => {
    if (rfbRef.current || !containerRef.current) return;

    setState(prev => ({ ...prev, status: 'connecting', error: null }));

    const token = localStorage.getItem('access_token');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/vnc/ws/${vmId}?token=${encodeURIComponent(token || '')}`;

    try {
      // Dynamic import to avoid top-level await issues with noVNC
      const { default: RFB } = await import('@novnc/novnc/lib/rfb');

      const rfb = new RFB(containerRef.current, wsUrl, {
        wsProtocols: ['binary'],
      });

      rfb.viewOnly = viewOnly;
      rfb.scaleViewport = scaleViewport;
      rfb.clipViewport = clipViewport;
      rfb.showDotCursor = showDotCursor;
      rfb.qualityLevel = qualityLevel;
      rfb.compressionLevel = compressionLevel;

      rfb.addEventListener('connect', () => {
        setState(prev => ({ ...prev, status: 'connected' }));
      });

      rfb.addEventListener('disconnect', (e: Event) => {
        const detail = (e as CustomEvent).detail || {};
        setState(prev => ({
          ...prev,
          status: detail.clean ? 'disconnected' : 'error',
          error: detail.clean ? null : 'Connexion perdue',
        }));
        rfbRef.current = null;
      });

      rfb.addEventListener('securityfailure', (e: Event) => {
        const detail = (e as CustomEvent).detail || {};
        setState(prev => ({
          ...prev,
          status: 'error',
          error: `Erreur de securite: ${detail.reason || 'inconnue'}`,
        }));
      });

      rfbRef.current = rfb;
    } catch (err) {
      setState(prev => ({
        ...prev,
        status: 'error',
        error: err instanceof Error ? err.message : 'Impossible de creer la connexion VNC',
      }));
    }
  }, [vmId, viewOnly, scaleViewport, clipViewport, showDotCursor, qualityLevel, compressionLevel]);

  const disconnect = useCallback(() => {
    if (rfbRef.current) {
      rfbRef.current.disconnect();
      rfbRef.current = null;
    }
    setState(prev => ({ ...prev, status: 'disconnected', error: null }));
  }, []);

  const sendCtrlAltDel = useCallback(() => {
    rfbRef.current?.sendCtrlAltDel();
  }, []);

  const setViewOnly = useCallback((value: boolean) => {
    if (rfbRef.current) rfbRef.current.viewOnly = value;
  }, []);

  const setScaleViewport = useCallback((value: boolean) => {
    if (rfbRef.current) rfbRef.current.scaleViewport = value;
  }, []);

  const sendClipboard = useCallback((text: string) => {
    if (rfbRef.current) rfbRef.current.clipboardPasteFrom(text);
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      const timer = setTimeout(() => { connect(); }, 200);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [autoConnect, connect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (rfbRef.current) {
        rfbRef.current.disconnect();
        rfbRef.current = null;
      }
    };
  }, []);

  return {
    containerRef,
    state,
    connect,
    disconnect,
    sendCtrlAltDel,
    setViewOnly,
    setScaleViewport,
    sendClipboard,
  };
}
