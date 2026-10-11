// Cliente da API do mestre. Em produção a UI é servida pelo próprio mestre
// (mesma origem, base ""); no `npm run dev` aponte NEXT_PUBLIC_PROJMAP_API
// para o mestre (ex.: http://localhost:8100).
import type { MediaItem, Output, Project } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_PROJMAP_API ?? "";

export class ApiError extends Error {
  constructor(public status: number, public details: string[]) {
    super(details.join("; ") || `HTTP ${status}`);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let details: string[] = [];
    try {
      const body = await res.json();
      details = Array.isArray(body.detail) ? body.detail : [String(body.detail ?? res.statusText)];
    } catch {
      details = [res.statusText];
    }
    throw new ApiError(res.status, details);
  }
  return res.json() as Promise<T>;
}

export interface ProjectPayload {
  revision: number;
  project: Project;
}

export const api = {
  getProject: () => call<ProjectPayload>("/api/project"),
  putProject: (project: Project) =>
    call<{ revision: number }>("/api/project", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project }),
    }),
  patchOutput: (nodeId: string, changes: Partial<Output>) =>
    call<ProjectPayload>(`/api/nodes/${encodeURIComponent(nodeId)}/output`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),
  uploadMedia: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<{ revision: number; item: MediaItem }>("/api/media", { method: "POST", body: form });
  },
  uploadPhoto: (nodeId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<ProjectPayload>(`/api/nodes/${encodeURIComponent(nodeId)}/photo`, { method: "POST", body: form });
  },
  photoUrl: (nodeId: string, bust: string) => `${API_BASE}/api/nodes/${encodeURIComponent(nodeId)}/photo?v=${bust}`,
  exportUrl: () => `${API_BASE}/api/project/export`,
};
