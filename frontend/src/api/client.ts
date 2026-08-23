import type {
  ApiErrorBody,
  ChatTurnResponse,
  HealthResponse,
  Provider,
  SessionDetail,
  SessionSummary,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  component: string | null;
  status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.code = body.error.code;
    this.component = body.error.component;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });

  if (!response.ok) {
    let body: ApiErrorBody;
    try {
      const raw = await response.json();
      body = raw.detail ?? raw; // FastAPI wraps HTTPException(detail=...) under "detail"
    } catch {
      body = { error: { code: "unknown_error", message: response.statusText, component: null } };
    }
    throw new ApiError(response.status, body);
  }

  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  listSessions: () => request<SessionSummary[]>("/api/sessions"),

  createSession: (title?: string, userRef?: string) =>
    request<SessionSummary>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title, user_ref: userRef }),
    }),

  getSession: (id: string) => request<SessionDetail>(`/api/sessions/${id}`),

  sendMessage: (sessionId: string, content: string) =>
    request<ChatTurnResponse>(`/api/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  generateShip30: (sessionId: string, content: string) =>
    request<ChatTurnResponse>(`/api/sessions/${sessionId}/ship30`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  setProvider: (sessionId: string, provider: Provider) =>
    request<SessionSummary>(`/api/sessions/${sessionId}/provider`, {
      method: "PATCH",
      body: JSON.stringify({ provider }),
    }),

  listSources: () => request<unknown[]>("/api/sources"),
};
