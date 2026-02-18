"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";

export default function ProjectsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const authenticated = isAuthenticated();

  useEffect(() => {
    if (!authenticated) router.push("/login");
  }, [router, authenticated]);

  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
    enabled: authenticated,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => api.createProject(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setNewName("");
      setShowCreate(false);
    },
  });

  if (isLoading) {
    return <div className="p-8 text-center">Loading...</div>;
  }

  return (
    <main className="max-w-4xl mx-auto p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Projects</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
        >
          New Project
        </button>
      </div>

      {showCreate && (
        <div className="mb-6 p-4 border rounded-lg bg-gray-50">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate(newName);
            }}
            className="flex gap-3"
          >
            <input
              type="text"
              placeholder="Project name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
              className="flex-1 p-2 border rounded-lg"
            />
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg"
            >
              Create
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="px-4 py-2 border rounded-lg"
            >
              Cancel
            </button>
          </form>
        </div>
      )}

      {projects && projects.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          No projects yet. Create one to get started.
        </div>
      ) : (
        <div className="grid gap-4">
          {projects?.map((project) => (
            <Link
              key={project.id}
              href={`/projects/${project.id}`}
              className="block p-4 border rounded-lg hover:border-blue-300 hover:bg-blue-50 transition"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold">{project.name}</h2>
                  <p className="text-sm text-gray-500 font-mono">
                    {project.api_key.substring(0, 16)}...
                  </p>
                </div>
                <span className="text-sm text-gray-400">
                  {new Date(project.created_at).toLocaleDateString()}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
