// Cliente da API do mestre. Em produção a UI é servida pelo próprio mestre
// (mesma origem, base ""); no `npm run dev` aponte NEXT_PUBLIC_PROJMAP_API
// para o mestre (ex.: http://localhost:8100).
import type { DetectCandidate, InteractState, MediaItem, Output, Project, SourceSpec } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_PROJMAP_API ?? "";

// ---- token de pareamento (F6)
// O celular chega por http://<ip>:8100/remote/#t=<token> (QR do editor). O token
// fica no localStorage e vai em todo pedido; no próprio mestre ele é dispensado.
const TOKEN_KEY = "projmap.token";

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* navegação privada: o token vale só nesta aba */
  }
}

/** Lê ``#t=<token>`` da URL (vindo do QR), guarda e limpa o hash. */
export function adoptTokenFromHash() {
  const m = /[#&]t=([^&]+)/.exec(window.location.hash);
  if (!m) return;
  setToken(decodeURIComponent(m[1]));
  history.replaceState(null, "", window.location.pathname + window.location.search);
}

/** Para URLs usadas em <img>/<video>/WebSocket, que não mandam cabeçalho. */
export function withToken(url: string): string {
  const t = getToken();
  if (!t) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(t)}`;
}

export class ApiError extends Error {
  constructor(public status: number, public details: string[]) {
    super(details.join("; ") || `HTTP ${status}`);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("X-ProjMap-Token", token);
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
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
  health: () => call<{ ok: boolean; version: string; revision: number }>("/api/health"),
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
  detect: (nodeId: string, sensitivity: number) =>
    call<{ detector: string; candidates: DetectCandidate[] }>(`/api/nodes/${encodeURIComponent(nodeId)}/detect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sensitivity }),
    }),
  photoUrl: (nodeId: string, bust: string) =>
    withToken(`${API_BASE}/api/nodes/${encodeURIComponent(nodeId)}/photo?v=${bust}`),
  exportUrl: () => withToken(`${API_BASE}/api/project/export`),

  // remote no celular (F6)
  patchSurface: (id: string, changes: { visible?: boolean; opacity?: number; source?: Partial<SourceSpec> }) =>
    call<ProjectPayload>(`/api/surfaces/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),
  saveLook: (name: string) =>
    call<ProjectPayload>("/api/looks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  recallLook: (id: string) =>
    call<ProjectPayload & { skipped: string[] }>(`/api/looks/${encodeURIComponent(id)}/recall`, { method: "POST" }),
  deleteLook: (id: string) => call<ProjectPayload>(`/api/looks/${encodeURIComponent(id)}`, { method: "DELETE" }),
  pairInfo: () => call<{ url: string; token: string | null; lan: boolean; qr_svg: string | null }>("/api/remote/pair"),

  // camada interativa
  interactState: () => call<InteractState>("/api/interact/state"),
  interactPresets: () => call<Record<string, { title: string; description: string }>>("/api/interact/presets"),
  interactPreset: (name: string) => call<InteractState>(`/api/interact/presets/${encodeURIComponent(name)}`, { method: "POST" }),
  interactGenerate: (text: string, useLlm: boolean) =>
    call<InteractState>("/api/interact/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, use_llm: useLlm }),
    }),
  interactPlayer: (p: { x?: number; distance?: number; yaw_deg?: number; tracked?: boolean }) =>
    call<InteractState>("/api/interact/player", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(p),
    }),
  interactAuto: () => call<InteractState>("/api/interact/player/auto", { method: "POST" }),
  interactReset: () => call<InteractState>("/api/interact/reset", { method: "POST" }),
  interactPause: (paused: boolean) => call<InteractState>(`/api/interact/pause?paused=${paused}`, { method: "POST" }),
  interactDebug: (on: boolean) => call<InteractState>(`/api/interact/debug?on=${on}`, { method: "POST" }),
};
