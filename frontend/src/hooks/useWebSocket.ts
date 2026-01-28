import { useEffect, useRef, useState, useCallback } from 'react';

// Types
export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface WebSocketMessage<T = unknown> {
  type: string;
  payload: T;
  timestamp?: string;
}

export interface DeploymentProgressPayload {
  deployment_id: string;
  status: string;
  progress: number;
  current_step: string;
  message?: string;
}

export interface VMStatePayload {
  vm_id: string;
  name: string;
  state: string;
  previous_state?: string;
}

export interface NotificationPayload {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
}

export interface UseWebSocketOptions {
  url?: string;
  reconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  onMessage?: (message: WebSocketMessage) => void;
}

export interface UseWebSocketReturn {
  status: WebSocketStatus;
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  send: (message: WebSocketMessage) => void;
  subscribe: (room: string) => void;
  unsubscribe: (room: string) => void;
  reconnect: () => void;
  disconnect: () => void;
}

const DEFAULT_WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1/realtime/ws`;

/**
 * Hook pour gérer les connexions WebSocket avec reconnexion automatique
 */
export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    url = DEFAULT_WS_URL,
    reconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    onOpen,
    onClose,
    onError,
    onMessage,
  } = options;

  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const subscribedRoomsRef = useRef<Set<string>>(new Set());

  // Nettoyer le timeout de reconnexion
  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  // Connexion WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    setStatus('connecting');
    
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        reconnectAttemptsRef.current = 0;
        
        // Re-souscrire aux rooms précédentes avec le format attendu par le backend
        subscribedRoomsRef.current.forEach((room) => {
          ws.send(JSON.stringify({ action: 'join_room', room: room }));
        });
        
        onOpen?.();
      };

      ws.onclose = () => {
        setStatus('disconnected');
        wsRef.current = null;
        onClose?.();
        
        // Reconnexion automatique
        if (reconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval * reconnectAttemptsRef.current);
        }
      };

      ws.onerror = (error) => {
        setStatus('error');
        onError?.(error);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketMessage;
          setLastMessage(message);
          onMessage?.(message);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };
    } catch (err) {
      console.error('WebSocket connection error:', err);
      setStatus('error');
    }
  }, [url, reconnect, reconnectInterval, maxReconnectAttempts, onOpen, onClose, onError, onMessage]);

  // Déconnexion
  const disconnect = useCallback(() => {
    clearReconnectTimeout();
    reconnectAttemptsRef.current = maxReconnectAttempts; // Empêcher la reconnexion
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setStatus('disconnected');
  }, [clearReconnectTimeout, maxReconnectAttempts]);

  // Reconnexion manuelle
  const reconnectManual = useCallback(() => {
    disconnect();
    reconnectAttemptsRef.current = 0;
    connect();
  }, [disconnect, connect]);

  // Envoyer un message
  const send = useCallback((message: WebSocketMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  // S'abonner à une room
  const subscribe = useCallback((room: string) => {
    subscribedRoomsRef.current.add(room);
    
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Format attendu par le backend : {"action": "join_room", "room": "..."}
      wsRef.current.send(JSON.stringify({
        action: 'join_room',
        room: room,
      }));
    }
  }, []);

  // Se désabonner d'une room
  const unsubscribe = useCallback((room: string) => {
    subscribedRoomsRef.current.delete(room);
    
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Format attendu par le backend : {"action": "leave_room", "room": "..."}
      wsRef.current.send(JSON.stringify({
        action: 'leave_room',
        room: room,
      }));
    }
  }, []);

  // Connexion automatique au montage
  useEffect(() => {
    connect();
    
    return () => {
      clearReconnectTimeout();
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect, clearReconnectTimeout]);

  return {
    status,
    isConnected: status === 'connected',
    lastMessage,
    send,
    subscribe,
    unsubscribe,
    reconnect: reconnectManual,
    disconnect,
  };
}

/**
 * Hook spécialisé pour les événements de déploiement
 */
export function useDeploymentEvents(
  deploymentId?: string,
  onProgress?: (progress: DeploymentProgressPayload) => void
) {
  const [progress, setProgress] = useState<DeploymentProgressPayload | null>(null);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    // Normaliser le format du message (support backend et frontend)
    const messageType = (message as any).type || (message as any).event_type || message.type;
    const messagePayload = (message as any).payload || (message as any).data || message.payload;
    
    // Normaliser le type (deployment.progress -> deployment_progress)
    const normalizedType = messageType?.replace(/\./g, '_');
    
    // Accepter les événements de progression de déploiement
    if (normalizedType === 'deployment_progress' || 
        normalizedType === 'deployment_created' ||
        normalizedType === 'deployment_started' ||
        normalizedType === 'deployment_completed' ||
        normalizedType === 'deployment_failed' ||
        normalizedType === 'deployment_cancelled' ||
        normalizedType === 'deployment_step_completed') {
      
      const payload = messagePayload as DeploymentProgressPayload;
      
      if (!deploymentId || payload.deployment_id === deploymentId) {
        setProgress(payload);
        onProgress?.(payload);
      }
    }
  }, [deploymentId, onProgress]);

  const { status, isConnected, subscribe, unsubscribe } = useWebSocket({
    onMessage: handleMessage,
  });

  useEffect(() => {
    if (isConnected) {
      if (deploymentId) {
        subscribe(`deployment:${deploymentId}`);
      } else {
        subscribe('deployments');
      }
    }

    return () => {
      if (deploymentId) {
        unsubscribe(`deployment:${deploymentId}`);
      } else {
        unsubscribe('deployments');
      }
    };
  }, [isConnected, deploymentId, subscribe, unsubscribe]);

  return { status, isConnected, progress };
}

/**
 * Hook spécialisé pour les événements de VM
 */
export function useVMEvents(
  vmId?: string,
  onStateChange?: (state: VMStatePayload) => void
) {
  const [vmState, setVMState] = useState<VMStatePayload | null>(null);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'vm_state_change') {
      const payload = message.payload as VMStatePayload;
      
      if (!vmId || payload.vm_id === vmId) {
        setVMState(payload);
        onStateChange?.(payload);
      }
    }
  }, [vmId, onStateChange]);

  const { status, isConnected, subscribe, unsubscribe } = useWebSocket({
    onMessage: handleMessage,
  });

  useEffect(() => {
    if (isConnected) {
      subscribe('vms');
    }

    return () => {
      unsubscribe('vms');
    };
  }, [isConnected, subscribe, unsubscribe]);

  return { status, isConnected, vmState };
}

/**
 * Hook spécialisé pour les notifications temps réel
 */
export function useNotifications(
  onNotification?: (notification: NotificationPayload) => void
) {
  const [notifications, setNotifications] = useState<NotificationPayload[]>([]);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'notification') {
      const payload = message.payload as NotificationPayload;
      setNotifications((prev) => [payload, ...prev].slice(0, 50)); // Garder les 50 dernières
      onNotification?.(payload);
    }
  }, [onNotification]);

  const { status, isConnected, subscribe, unsubscribe } = useWebSocket({
    onMessage: handleMessage,
  });

  useEffect(() => {
    if (isConnected) {
      subscribe('notifications');
    }

    return () => {
      unsubscribe('notifications');
    };
  }, [isConnected, subscribe, unsubscribe]);

  const clearNotifications = useCallback(() => {
    setNotifications([]);
  }, []);

  return { status, isConnected, notifications, clearNotifications };
}

export default useWebSocket;
