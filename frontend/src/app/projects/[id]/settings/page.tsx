"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";

export default function SettingsPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const projectId = Number(params.id);
  const authenticated = isAuthenticated();

  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [copied, setCopied] = useState<string | null>(null);
  const [showDelete, setShowDelete] = useState(false);

  useEffect(() => {
    if (!authenticated) router.push("/login");
  }, [router, authenticated]);

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    enabled: authenticated,
  });

  useEffect(() => {
    if (project) {
      setName(project.name);
      setDomain(project.domain || "");
    }
  }, [project]);

  const updateMutation = useMutation({
    mutationFn: (data: { name?: string; domain?: string }) =>
      api.updateProject(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const rotateMutation = useMutation({
    mutationFn: () => api.rotateKey(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteProject(projectId),
    onSuccess: () => {
      router.push("/projects");
    },
  });

  function copyToClipboard(text: string, label: string) {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  }

  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const snippet = `<script>
(function(){
  var s=document.createElement("script");
  s.src="${apiUrl}/static/sdk/tracker.min.js";
  s.setAttribute("data-project","${project?.api_key || "YOUR_API_KEY"}");
  s.setAttribute("data-api-url","${apiUrl}");
  document.head.appendChild(s);
})();
</script>`;

  return (
    <main className="max-w-3xl mx-auto p-8">
      <div className="mb-6">
        <Link
          href={`/projects/${projectId}`}
          className="text-sm text-blue-600 hover:underline"
        >
          Dashboard
        </Link>
        <h1 className="text-2xl font-bold">Project Settings</h1>
      </div>

      {/* Project Info */}
      <section className="border rounded-lg p-6 mb-6 bg-white">
        <h2 className="font-semibold mb-4">General</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateMutation.mutate({ name, domain: domain || undefined });
          }}
          className="space-y-4"
        >
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Project Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full p-2 border rounded-lg"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Domain (optional)
            </label>
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="example.com"
              className="w-full p-2 border rounded-lg"
            />
          </div>
          <button
            type="submit"
            disabled={updateMutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {updateMutation.isPending ? "Saving..." : "Save Changes"}
          </button>
          {updateMutation.isSuccess && (
            <span className="text-sm text-green-600 ml-3">Saved</span>
          )}
        </form>
      </section>

      {/* API Key */}
      <section className="border rounded-lg p-6 mb-6 bg-white">
        <h2 className="font-semibold mb-4">API Key</h2>
        <div className="flex items-center gap-3 mb-4">
          <code className="flex-1 p-3 bg-gray-100 rounded-lg text-sm font-mono break-all">
            {project?.api_key || "Loading..."}
          </code>
          <button
            onClick={() =>
              project && copyToClipboard(project.api_key, "api-key")
            }
            className="px-3 py-2 border rounded-lg text-sm hover:bg-gray-50 shrink-0"
          >
            {copied === "api-key" ? "Copied" : "Copy"}
          </button>
        </div>
        <button
          onClick={() => {
            if (
              confirm(
                "Rotate API key? The old key will stop working immediately.",
              )
            ) {
              rotateMutation.mutate();
            }
          }}
          disabled={rotateMutation.isPending}
          className="px-4 py-2 border border-orange-300 text-orange-600 rounded-lg text-sm hover:bg-orange-50"
        >
          {rotateMutation.isPending ? "Rotating..." : "Rotate API Key"}
        </button>
      </section>

      {/* Tracking Snippet */}
      <section className="border rounded-lg p-6 mb-6 bg-white">
        <h2 className="font-semibold mb-4">Tracking Snippet</h2>
        <p className="text-sm text-gray-600 mb-3">
          Add this snippet to the {"<head>"} of your website to start tracking
          events.
        </p>
        <div className="relative">
          <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto">
            {snippet}
          </pre>
          <button
            onClick={() => copyToClipboard(snippet, "snippet")}
            className="absolute top-2 right-2 px-2 py-1 bg-gray-700 text-gray-200 rounded text-xs hover:bg-gray-600"
          >
            {copied === "snippet" ? "Copied" : "Copy"}
          </button>
        </div>
      </section>

      {/* SDK Usage */}
      <section className="border rounded-lg p-6 mb-6 bg-white">
        <h2 className="font-semibold mb-4">SDK Usage</h2>
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium text-gray-700">Track custom events:</p>
            <code className="block mt-1 p-2 bg-gray-100 rounded text-sm">
              {"tracker.event('button_click', { button_id: 'signup' });"}
            </code>
          </div>
          <div>
            <p className="font-medium text-gray-700">Identify users:</p>
            <code className="block mt-1 p-2 bg-gray-100 rounded text-sm">
              {"tracker.identify('user_42', { plan: 'pro' });"}
            </code>
          </div>
          <div>
            <p className="font-medium text-gray-700">Reset on logout:</p>
            <code className="block mt-1 p-2 bg-gray-100 rounded text-sm">
              {"tracker.reset();"}
            </code>
          </div>
        </div>
      </section>

      {/* Danger Zone */}
      <section className="border border-red-200 rounded-lg p-6 bg-white">
        <h2 className="font-semibold text-red-600 mb-4">Danger Zone</h2>
        {!showDelete ? (
          <button
            onClick={() => setShowDelete(true)}
            className="px-4 py-2 border border-red-300 text-red-600 rounded-lg text-sm hover:bg-red-50"
          >
            Delete Project
          </button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-red-600">
              This will permanently delete the project and all its data. This
              action cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending
                  ? "Deleting..."
                  : "Confirm Delete"}
              </button>
              <button
                onClick={() => setShowDelete(false)}
                className="px-4 py-2 border rounded-lg text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
