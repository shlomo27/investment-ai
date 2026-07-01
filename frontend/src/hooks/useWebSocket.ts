import { useEffect, useRef, useCallback } from "react";
import { useAppDispatch } from "../store";
import { addRealtimeNotification } from "../store/slices/notificationsSlice";

const rawBase = import.meta.env.VITE_API_URL || `${location.protocol}//${location.host}`;
const WS_BASE = rawBase.replace(/^https/, "wss").replace(/^http/, "ws");
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECTS = 5;

export type WsMessage =
  | { type: "connected"; user_id: number }
  | { type: "heartbeat" }
  | { type: "pong" }
  | { type: "notification"; data: any }
  | { type: "price_alert"; symbol: string; direction: string; price: number }
  | { type: "ta_signal"; symbol: string; signal: string; score: number };

interface Options {
  onMessage?: (msg: WsMessage) => void;
  enabled?: boolean;
}

export function useWebSocket(userId: number | undefined, opts: Options = {}) {
  const dispatch = useAppDispatch();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCount = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const enabled = opts.enabled !== false;

  const connect = useCallback(() => {
    if (!userId || !enabled) return;
    const token = localStorage.getItem("access_token");
    if (!token) return;

    const url = `${WS_BASE}/ws/${userId}?token=${token}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectCount.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        if (msg.type === "heartbeat" && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
          return;
        }
        if (msg.type === "notification" && msg.data) {
          dispatch(addRealtimeNotification(msg.data));
        }
        opts.onMessage?.(msg);
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (reconnectCount.current < MAX_RECONNECTS && enabled) {
        reconnectCount.current += 1;
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS * reconnectCount.current);
      }
    };

    ws.onerror = () => ws.close();
  }, [userId, enabled, dispatch, opts.onMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { send };
}
