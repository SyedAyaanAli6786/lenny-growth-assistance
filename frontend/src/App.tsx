import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "./api/client";
import { ArtifactViewer } from "./components/ArtifactViewer";
import { MessageInput } from "./components/MessageInput";
import { MessageList } from "./components/MessageList";
import { ProviderToggle } from "./components/ProviderToggle";
import { SessionSidebar } from "./components/SessionSidebar";
import type { ArtifactData, HealthResponse, Provider, SessionDetail, SessionSummary } from "./types";

function pseudoUserId(): string {
  const key = "lenny_user_ref";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

export default function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<SessionDetail | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [artifact, setArtifact] = useState<ArtifactData | null>(null);
  const [pendingLabel, setPendingLabel] = useState<string | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [providerPending, setProviderPending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const refreshHealth = useCallback(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    refreshHealth();
    const interval = setInterval(refreshHealth, 15000);
    return () => clearInterval(interval);
  }, [refreshHealth]);

  const loadSessions = useCallback(async () => {
    const list = await api.listSessions();
    setSessions(list);
    return list;
  }, []);

  const openSession = useCallback(async (id: string) => {
    const detail = await api.getSession(id);
    setActiveSession(detail);
    setArtifact(null);
    setErrorText(null);
    setSidebarOpen(false);
  }, []);

  useEffect(() => {
    loadSessions().then((list) => {
      if (list.length > 0) openSession(list[0].id);
    });
  }, [loadSessions, openSession]);

  const handleNewSession = useCallback(async () => {
    const session = await api.createSession(undefined, pseudoUserId());
    await loadSessions();
    await openSession(session.id);
  }, [loadSessions, openSession]);

  const handleProviderChange = useCallback(
    async (provider: Provider) => {
      if (!activeSession) return;
      setProviderPending(true);
      setErrorText(null);
      try {
        const updated = await api.setProvider(activeSession.id, provider);
        setActiveSession((prev) => (prev ? { ...prev, llm_provider: updated.llm_provider, llm_model: updated.llm_model } : prev));
      } catch (err) {
        setErrorText(err instanceof ApiError ? err.message : "Could not switch provider.");
      } finally {
        setProviderPending(false);
      }
    },
    [activeSession],
  );

  const runTurn = useCallback(
    async (content: string, kind: "message" | "ship30") => {
      if (!activeSession) return;
      setErrorText(null);
      setPendingLabel(
        kind === "ship30"
          ? `Drafting Ship 30 essay… (${activeSession.llm_provider})`
          : `${activeSession.llm_provider === "ollama" ? "Ollama" : "Claude"} is thinking…`,
      );

      // Optimistic user bubble so the UI feels responsive before the reply lands.
      const optimisticUser = {
        id: `optimistic-${Date.now()}`,
        role: "user" as const,
        content,
        provider: null,
        citations: [],
        created_at: new Date().toISOString(),
      };
      setActiveSession((prev) => (prev ? { ...prev, messages: [...prev.messages, optimisticUser] } : prev));

      try {
        const turn = kind === "ship30" ? await api.generateShip30(activeSession.id, content) : await api.sendMessage(activeSession.id, content);
        setActiveSession((prev) => (prev ? { ...prev, messages: [...prev.messages, turn.message] } : prev));
        if (turn.artifact) setArtifact(turn.artifact);
      } catch (err) {
        setErrorText(
          err instanceof ApiError
            ? `${err.message}${err.component ? ` (${err.component})` : ""}`
            : "Something went wrong talking to the backend.",
        );
      } finally {
        setPendingLabel(null);
      }
    },
    [activeSession],
  );

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded p-1.5 text-slate-500 hover:bg-slate-100 md:hidden"
            onClick={() => setSidebarOpen((o) => !o)}
            aria-label="Toggle sessions"
          >
            ☰
          </button>
          <span className="text-sm font-semibold">Lenny Growth Assistant</span>
        </div>
        {activeSession && (
          <ProviderToggle
            current={activeSession.llm_provider}
            health={health}
            onChange={handleProviderChange}
            pending={providerPending}
          />
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        <div className={`${sidebarOpen ? "block" : "hidden"} absolute z-10 h-[calc(100%-45px)] md:relative md:block`}>
          <SessionSidebar sessions={sessions} activeId={activeSession?.id ?? null} onSelect={openSession} onNew={handleNewSession} />
        </div>

        <main className="flex min-w-0 flex-1 flex-col bg-slate-50">
          <MessageList messages={activeSession?.messages ?? []} pendingLabel={pendingLabel} errorText={errorText} />
          <MessageInput
            disabled={!activeSession || !!pendingLabel}
            onSend={(text) => runTurn(text, "message")}
            onShip30={(text) => runTurn(text, "ship30")}
          />
        </main>

        {artifact && (
          <div className="fixed inset-0 z-20 md:static md:inset-auto">
            <ArtifactViewer artifact={artifact} onClose={() => setArtifact(null)} />
          </div>
        )}
      </div>
    </div>
  );
}
