"use client";

import { useLiveEvents } from "@/lib/ws";

export function EventFeed({ projectId, token }: { projectId: number; token: string | null }) {
  const { events, connected } = useLiveEvents(projectId, token);

  return (
    <div className="border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Live Events</h3>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            connected ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
          }`}
        >
          {connected ? "Connected" : "Disconnected"}
        </span>
      </div>
      {events.length === 0 ? (
        <p className="text-gray-400 text-sm">Waiting for events...</p>
      ) : (
        <ul className="space-y-2 max-h-96 overflow-y-auto">
          {events.map((evt, i) => (
            <li key={i} className="text-sm border-b pb-2 last:border-0">
              <div className="flex items-center justify-between">
                <span className="font-mono font-medium">{evt.event_name}</span>
                <span className="text-gray-400 text-xs">
                  {new Date(evt.timestamp).toLocaleTimeString()}
                </span>
              </div>
              {evt.page_url && (
                <p className="text-gray-500 text-xs truncate">{evt.page_url}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
