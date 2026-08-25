import type {
  ApiErrorBody,
  ChatTurnResponse,
  HealthResponse,
  Provider,
  SessionDetail,
  SessionSummary,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:3400";

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

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone: (turn: ChatTurnResponse) => void;
  onError: (message: string) => void;
}

interface Ship30StreamHandlers extends StreamHandlers {
  // A failed draft is about to be regenerated via the repair prompt — clear
  // whatever's been shown so far instead of appending the repair's text
  // after the discarded draft's.
  onRestart: () => void;
}

/**
 * Shared by streamMessage/streamShip30: consumes a newline-delimited-JSON
 * response body, one {type: ..., ...} event per line, dispatching each
 * parsed event to `onEvent`. NDJSON over a plain POST body rather than a
 * native EventSource: these requests need a JSON body (the message
 * content), and EventSource only supports GET.
 */
async function consumeNdjsonStream(url: string, body: unknown, onEvent: (event: any) => void, onError: (message: string) => void): Promise<void> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    onError("Could not reach the backend.");
    return;
  }

  if (!response.ok || !response.body) {
    // A failure here means the request never reached the streaming
    // generator at all (validation error, session not found) — the backend
    // still returns its normal structured JSON error shape in that case.
    try {
      const raw = await response.json();
      const errorBody: ApiErrorBody = raw.detail ?? raw;
      onError(errorBody.error.message);
    } catch {
      onError(response.statusText || "Something went wrong talking to the backend.");
    }
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex = buffer.indexOf("\n");
    while (newlineIndex >= 0) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (line) onEvent(JSON.parse(line));
      newlineIndex = buffer.indexOf("\n");
    }
  }
}

async function streamMessage(sessionId: string, content: string, handlers: StreamHandlers): Promise<void> {
  await consumeNdjsonStream(
    `${BASE_URL}/api/sessions/${sessionId}/messages/stream`,
    { content },
    (event) => {
      if (event.type === "delta") handlers.onDelta(event.text);
      else if (event.type === "done") handlers.onDone(event.turn);
      else if (event.type === "error") handlers.onError(event.message);
    },
    handlers.onError,
  );
}

async function streamShip30(sessionId: string, content: string, handlers: Ship30StreamHandlers): Promise<void> {
  await consumeNdjsonStream(
    `${BASE_URL}/api/sessions/${sessionId}/ship30/stream`,
    { content },
    (event) => {
      if (event.type === "delta") handlers.onDelta(event.text);
      else if (event.type === "restart") handlers.onRestart();
      else if (event.type === "done") handlers.onDone(event.turn);
      else if (event.type === "error") handlers.onError(event.message);
    },
    handlers.onError,
  );
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

  deleteSession: (id: string) => request<void>(`/api/sessions/${id}`, { method: "DELETE" }),

  sendMessage: (sessionId: string, content: string) =>
    request<ChatTurnResponse>(`/api/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  streamMessage,

  stopMessage: (sessionId: string) => request<void>(`/api/sessions/${sessionId}/messages/stop`, { method: "POST" }),

  streamShip30,

  setProvider: (sessionId: string, provider: Provider) =>
    request<SessionSummary>(`/api/sessions/${sessionId}/provider`, {
      method: "PATCH",
      body: JSON.stringify({ provider }),
    }),

  listSources: () => request<unknown[]>("/api/sources"),
};
