"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { getToken, isAuthenticated } from "@/lib/auth";
import { MetricCard } from "@/components/dashboard";

export default function DashboardPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const [period, setPeriod] = useState("24h");
  const token = getToken();

  useEffect(() => {
    if (!isAuthenticated()) router.push("/login");
  }, [router]);

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(token!, projectId),
    enabled: !!token,
  });

  const { data: overview } = useQuery({
    queryKey: ["overview", projectId, period],
    queryFn: () => api.getOverview(token!, projectId, period),
    enabled: !!token,
    refetchInterval: 30000,
  });

  const { data: topEvents } = useQuery({
    queryKey: ["topEvents", projectId, period],
    queryFn: () => api.getTopEvents(token!, projectId, period),
    enabled: !!token,
    refetchInterval: 30000,
  });

  const { data: timeseries } = useQuery({
    queryKey: ["timeseries", projectId, period],
    queryFn: () =>
      api.getTimeseries(token!, projectId, period, period === "24h" ? "hourly" : "daily"),
    enabled: !!token,
    refetchInterval: 30000,
  });

  return (
    <main className="max-w-6xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link href="/projects" className="text-sm text-blue-600 hover:underline">
            Projects
          </Link>
          <h1 className="text-2xl font-bold">{project?.name || "Loading..."}</h1>
        </div>
        <div className="flex gap-2">
          {["24h", "7d", "30d"].map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 rounded-lg text-sm font-medium ${
                period === p
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {p}
            </button>
          ))}
          <Link
            href={`/projects/${projectId}/settings`}
            className="px-3 py-1 rounded-lg text-sm font-medium bg-gray-100 text-gray-600 hover:bg-gray-200"
          >
            Settings
          </Link>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <MetricCard label="Total Events" value={overview?.total_events ?? 0} />
        <MetricCard label="Unique Sessions" value={overview?.unique_sessions ?? 0} />
        <MetricCard label="Unique Users" value={overview?.unique_users ?? 0} />
        <MetricCard label="Top Event" value={overview?.top_event ?? "-"} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Timeseries */}
        <div className="border rounded-lg p-4">
          <h3 className="font-semibold mb-3">Events Over Time</h3>
          {timeseries?.data && timeseries.data.length > 0 ? (
            <div className="space-y-1">
              {timeseries.data.slice(-12).map((point, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <span className="text-gray-500 w-32 shrink-0">
                    {new Date(point.timestamp).toLocaleString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                    })}
                  </span>
                  <div
                    className="bg-blue-500 h-5 rounded"
                    style={{
                      width: `${Math.max(
                        4,
                        (point.count / Math.max(...timeseries.data.map((d) => d.count))) * 100
                      )}%`,
                    }}
                  />
                  <span className="text-gray-700 font-medium">{point.count}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-400 text-sm">No data yet</p>
          )}
        </div>

        {/* Top Events */}
        <div className="border rounded-lg p-4">
          <h3 className="font-semibold mb-3">Top Events</h3>
          {topEvents?.data && topEvents.data.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="py-2">Event</th>
                  <th className="py-2 text-right">Count</th>
                  <th className="py-2 text-right">Sessions</th>
                  <th className="py-2 text-right">Users</th>
                </tr>
              </thead>
              <tbody>
                {topEvents.data.map((evt) => (
                  <tr key={evt.event_name} className="border-b last:border-0">
                    <td className="py-2 font-mono">{evt.event_name}</td>
                    <td className="py-2 text-right">{evt.count}</td>
                    <td className="py-2 text-right">{evt.unique_sessions}</td>
                    <td className="py-2 text-right">{evt.unique_users}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-gray-400 text-sm">No data yet</p>
          )}
        </div>
      </div>
    </main>
  );
}
