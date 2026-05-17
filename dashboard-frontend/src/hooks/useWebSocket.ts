import { useState, useEffect, useRef, useCallback } from 'react';

export interface LogEntry {
  level: string;
  message: string;
  server_id?: string;
  timestamp?: string;
  source?: string;
  [key: string]: unknown;
}

interface UseWebSocketOptions {
  url: string;
  token: string | null;
  autoConnect?: boolean;
}

export function useWebSocket({ url, token, autoConnect = true }: UseWebSocketOptions) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const connectRef = useRef<() => void>(undefined);


  const connect = useCallback(() => {
    if (!token) return;
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${url}?token=${token}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (wsRef.current !== ws) return;
      setConnected(true);
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      if (wsRef.current !== ws) return;
      try {
        const entry = JSON.parse(event.data) as LogEntry;
        setLogs((prev) => [...prev.slice(-499), entry]);
      } catch { /* ignore malformed messages */ }
    };

    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      setConnected(false);
      // Auto-reconnect after 3 seconds
      reconnectRef.current = window.setTimeout(() => {
        connectRef.current?.();
      }, 3000);
    };

    ws.onerror = () => {
      if (wsRef.current !== ws) return;
      ws.close();
    };
    wsRef.current = ws;
  }, [url, token]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    let timeoutId: number;
    if (autoConnect) {
      // Delay connection slightly to bypass React 18 Strict Mode immediate unmount
      timeoutId = window.setTimeout(connect, 50);
    }
    return () => {
      if (timeoutId) window.clearTimeout(timeoutId);
      wsRef.current?.close();
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
    };
  }, [connect, autoConnect]);

  const sendFilter = useCallback((filters: Record<string, string | null>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(filters));
    }
  }, []);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { logs, connected, sendFilter, clearLogs };
}
