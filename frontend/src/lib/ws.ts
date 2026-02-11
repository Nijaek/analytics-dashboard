"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface LiveEvent {
  id: string;
  event_name: string;
  properties: Record<string, unknown> | null;
  session_id: string | null;
  distinct_id: string | null;
  page_url: string | null;
  timestamp: string;
}

const WS_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
  .replace("http://", "ws://")
  .replace("https://", "wss://");

const MAX_RETRIES = 10;
const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;

let eventCounter = 0;

export function useLiveEvents(projectId: number, token: string | null) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!token || !projectId) return;

    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket(
      `${WS_URL}/api/v1/ws/events/${projectId}?token=${token}`
    );

    ws.onopen = () => {
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onclose = () => {
      setConnected(false);
      if (retriesRef.current < MAX_RETRIES) {
        const delay = Math.min(
          BASE_DELAY_MS * Math.pow(2, retriesRef.current),
          MAX_DELAY_MS
        );
        retriesRef.current += 1;
        timerRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      // onclose fires after onerror and handles reconnection
    };

    ws.onmessage = (event) => {
      try {
        const raw = JSON.parse(event.data);
        const data: LiveEvent = {
          ...raw,
          id: `evt_${Date.now()}_${++eventCounter}`,
        };
        setEvents((prev) => [data, ...prev].slice(0, 100));
      } catch {
        // ignore parse errors
      }
    };

    wsRef.current = ws;
  }, [projectId, token]);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { events, connected };
}
