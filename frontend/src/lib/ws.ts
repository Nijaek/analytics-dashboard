"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface LiveEvent {
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

export function useLiveEvents(projectId: number, token: string | null) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (!token || !projectId) return;

    const ws = new WebSocket(
      `${WS_URL}/api/v1/ws/events/${projectId}?token=${token}`
    );

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as LiveEvent;
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
      wsRef.current?.close();
    };
  }, [connect]);

  return { events, connected };
}
