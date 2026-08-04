// Cliente da API FastAPI (server.py).

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Scene = {
  narration: string;
  visual_prompt: string;
  duration_s: number;
};

export type IdeaStatus = "pending" | "approved" | "rejected" | "posted";

export type Idea = {
  id: string;
  prompt: string;
  title: string;
  scenes: Scene[];
  status: IdeaStatus;
  mode: "manual" | "auto";
  video_path: string | null;
  note: string;
  created_at: string;
  decided_at: string | null;
};

export type Counts = Record<string, number>;

export type GenerateResult = {
  mode: "manual" | "auto";
  generated: number;
  posted: number;
  ideas: Idea[];
};

export type Column = { id: string; label: string };

export type Card = {
  id: string;
  title: string;
  description: string;
  column: string;
  sprint: string;
  labels: string[];
  order: number;
  created_at: string;
  updated_at: string;
};

export type BoardPayload = { columns: Column[]; cards: Card[] };

export type Schedule = {
  enabled: boolean;
  every_minutes: number;
  max_per_run: number;
  render_before: boolean;
  simulate: boolean;
  last_run: string | null;
  last_result: string | null;
  running: boolean;
  next_run: string | null;
};

export type RunResult = {
  processed: number;
  posted: number;
  simulated: number;
  errors: number;
  details: { id: string; status: string; info: string | null }[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      ...init,
    });
  } catch {
    throw new Error(
      `Não foi possível falar com a API em ${API_BASE}. ` +
        "O servidor (uvicorn server:app) está rodando?"
    );
  }
  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* corpo não-JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),

  // Ideias --------------------------------------------------------------
  generate: (body: {
    prompt: string;
    mode: "manual" | "auto";
    count: number;
    num_scenes: number;
  }) =>
    request<GenerateResult>("/api/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listIdeas: (status?: IdeaStatus) =>
    request<{ ideas: Idea[]; counts: Counts }>(
      `/api/ideas${status ? `?status=${status}` : ""}`
    ),

  approve: (id: string) =>
    request<Idea>(`/api/ideas/${id}/approve`, { method: "POST" }),

  reject: (id: string) =>
    request<Idea>(`/api/ideas/${id}/reject`, { method: "POST" }),

  post: (id: string) =>
    request<Idea>(`/api/ideas/${id}/post`, { method: "POST" }),

  render: (id: string) =>
    request<Idea>(`/api/ideas/${id}/render`, { method: "POST" }),

  videoUrl: (id: string) => `${API_BASE}/api/ideas/${id}/video`,

  clearDecided: () =>
    request<{ removed: number }>("/api/ideas/decided", { method: "DELETE" }),

  // Kanban --------------------------------------------------------------
  getBoard: () => request<BoardPayload>("/api/board"),

  createCard: (body: Partial<Card> & { title: string }) =>
    request<Card>("/api/board/cards", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateCard: (id: string, body: Partial<Card>) =>
    request<Card>(`/api/board/cards/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteCard: (id: string) =>
    request<{ deleted: string }>(`/api/board/cards/${id}`, {
      method: "DELETE",
    }),

  resetBoard: () =>
    request<BoardPayload>("/api/board/reset", { method: "POST" }),

  // Agendamento --------------------------------------------------------
  getSchedule: () => request<Schedule>("/api/schedule"),

  updateSchedule: (body: Partial<Schedule>) =>
    request<Schedule>("/api/schedule", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  runSchedule: () =>
    request<RunResult>("/api/schedule/run-now", { method: "POST" }),
};
