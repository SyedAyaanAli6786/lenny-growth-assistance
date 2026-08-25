export type Provider = "anthropic" | "ollama";

export interface Citation {
  source_id: string;
  chunk_id: string;
  title: string;
  guest: string | null;
  url: string | null;
  score: number;
}

export interface ArtifactData {
  id?: string;
  type: "markdown" | "html";
  title: string | null;
  content: string;
}

export interface MessageData {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  provider: string | null;
  citations: Citation[];
  created_at: string;
  artifact?: ArtifactData | null;
}

export interface SessionSummary {
  id: string;
  title: string | null;
  llm_provider: Provider;
  llm_model: string;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail extends SessionSummary {
  messages: MessageData[];
}

export interface ChatTurnResponse {
  message: MessageData;
  artifact: ArtifactData | null;
}

export interface ComponentHealth {
  status: "ok" | "degraded" | "down";
  detail: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "down";
  db: ComponentHealth;
  ollama: ComponentHealth;
  anthropic: ComponentHealth;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    component: string | null;
  };
}
