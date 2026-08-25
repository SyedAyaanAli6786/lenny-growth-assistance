import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "./api/client";
import { ArtifactViewer } from "./components/ArtifactViewer";
import { MessageInput } from "./components/MessageInput";
import { MessageList } from "./components/MessageList";
import { ProviderToggle } from "./components/ProviderToggle";
import { SessionSidebar } from "./components/SessionSidebar";
import { ThemeToggle } from "./components/ThemeToggle";
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

type Theme = "light" | "dark";

function initialTheme(): Theme {
  const stored = localStorage.getItem("lenny_theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<SessionDetail | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [artifact, setArtifact] = useState<ArtifactData | null>(null);
  // Keyed by session id, not a single global value: a generation in progress
  // belongs to the chat that started it, not to whatever chat happens to be
  // on screen when a delta or the final reply arrives. Previously these were
  // single top-level values, so switching chats mid-reply showed session A's
  // in-progress text overlaid on session B, disabled the input for every
  // chat regardless of which one was actually generating, and lost track of
  // a background reply the moment you navigated away from it.
  const [pendingBySession, setPendingBySession] = useState<Record<string, string>>({});
  const [streamingBySession, setStreamingBySession] = useState<Record<string, string>>({});
  const [errorBySession, setErrorBySession] = useState<Record<string, string>>({});
  // Only for an error with no session to scope it to yet (session creation
  // itself failing, before any session id exists).
  const [draftErrorText, setDraftErrorText] = useState<string | null>(null);
  const [providerPending, setProviderPending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("lenny_theme", theme);
  }, [theme]);

  const setPendingFor = useCallback((sessionId: string, label: string | null) => {
    setPendingBySession((prev) => {
      if (label === null) {
        if (!(sessionId in prev)) return prev;
        const next = { ...prev };
        delete next[sessionId];
        return next;
      }
      return { ...prev, [sessionId]: label };
    });
  }, []);

  const initStreamingFor = useCallback((sessionId: string) => {
    setStreamingBySession((prev) => ({ ...prev, [sessionId]: "" }));
  }, []);

  const appendStreamingFor = useCallback((sessionId: string, text: string) => {
    setStreamingBySession((prev) => ({ ...prev, [sessionId]: (prev[sessionId] ?? "") + text }));
  }, []);

  const clearStreamingFor = useCallback((sessionId: string) => {
    setStreamingBySession((prev) => {
      if (!(sessionId in prev)) return prev;
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
  }, []);

  const setErrorFor = useCallback((sessionId: string, message: string | null) => {
    setErrorBySession((prev) => {
      if (message === null) {
        if (!(sessionId in prev)) return prev;
        const next = { ...prev };
        delete next[sessionId];
        return next;
      }
      return { ...prev, [sessionId]: message };
    });
  }, []);

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
    setSidebarOpen(false);
  }, []);

  useEffect(() => {
    loadSessions().then((list) => {
      if (list.length > 0) openSession(list[0].id);
    });
  }, [loadSessions, openSession]);

  const handleNewSession = useCallback(() => {
    // Lazy creation: no backend row is created here at all — only when a
    // message actually gets sent (see runTurn below). Earlier this eagerly
    // created a session on click, guarded by "reuse it if the current chat
    // is still empty" — but that guard only covered the chat you were
    // already on. Switch to a different (non-empty) chat first, then click
    // "New chat," and the guard never fires: it created another empty
    // session every time, leaving a trail of orphaned "Untitled session"
    // rows behind (reported live: three in a row). Not creating anything
    // until there's an actual message removes the whole failure mode
    // instead of chasing more edge cases in the guard.
    setActiveSession(null);
    setArtifact(null);
    setDraftErrorText(null);
    setDraft("");
    setSidebarOpen(false);
  }, []);

  const reportError = useCallback(
    (message: string) => {
      if (activeSession) setErrorFor(activeSession.id, message);
      else setDraftErrorText(message);
    },
    [activeSession, setErrorFor],
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await api.deleteSession(id);
      } catch (err) {
        reportError(err instanceof ApiError ? err.message : "Could not delete this chat.");
        return;
      }
      const list = await loadSessions();
      if (activeSession?.id === id) {
        if (list.length > 0) await openSession(list[0].id);
        else {
          setActiveSession(null);
          setArtifact(null);
        }
      }
    },
    [activeSession, loadSessions, openSession, reportError],
  );

  const handleProviderChange = useCallback(
    async (provider: Provider) => {
      if (!activeSession) return;
      setProviderPending(true);
      setErrorFor(activeSession.id, null);
      try {
        const updated = await api.setProvider(activeSession.id, provider);
        setActiveSession((prev) => (prev ? { ...prev, llm_provider: updated.llm_provider, llm_model: updated.llm_model } : prev));
      } catch (err) {
        setErrorFor(activeSession.id, err instanceof ApiError ? err.message : "Could not switch provider.");
      } finally {
        setProviderPending(false);
      }
    },
    [activeSession, setErrorFor],
  );

  const runShip30 = useCallback(
    async (session: SessionDetail, content: string, wasUntitled: boolean) => {
      setPendingFor(session.id, `Drafting Ship 30 essay… (${session.llm_provider})`);
      initStreamingFor(session.id);

      await api.streamShip30(session.id, content, {
        onDelta: (text) => {
          setPendingFor(session.id, null);
          appendStreamingFor(session.id, text);
        },
        onRestart: () => {
          // The draft just failed validation and a repair pass is starting —
          // discard the failed draft's text instead of appending the
          // repair's deltas after it.
          setPendingFor(session.id, `Drafting Ship 30 essay… (${session.llm_provider})`);
          initStreamingFor(session.id);
        },
        onDone: (turn) => {
          setPendingFor(session.id, null);
          clearStreamingFor(session.id);
          setActiveSession((prev) => (prev && prev.id === session.id ? { ...prev, messages: [...prev.messages, turn.message] } : prev));
          if (turn.artifact) setArtifact(turn.artifact);
          if (wasUntitled) loadSessions();
        },
        onError: (message) => {
          setPendingFor(session.id, null);
          clearStreamingFor(session.id);
          setErrorFor(session.id, message);
        },
      });
    },
    [loadSessions, setPendingFor, initStreamingFor, appendStreamingFor, clearStreamingFor, setErrorFor],
  );

  const runMessage = useCallback(
    async (session: SessionDetail, content: string, wasUntitled: boolean) => {
      setPendingFor(session.id, `${session.llm_provider === "ollama" ? "Ollama" : "Claude"} is thinking…`);
      initStreamingFor(session.id);

      await api.streamMessage(session.id, content, {
        onDelta: (text) => {
          setPendingFor(session.id, null);
          appendStreamingFor(session.id, text);
        },
        onDone: (turn) => {
          setPendingFor(session.id, null);
          clearStreamingFor(session.id);
          setActiveSession((prev) => (prev && prev.id === session.id ? { ...prev, messages: [...prev.messages, turn.message] } : prev));
          if (turn.artifact) setArtifact(turn.artifact);
          if (wasUntitled) loadSessions();
        },
        onError: (message) => {
          setPendingFor(session.id, null);
          clearStreamingFor(session.id);
          setErrorFor(session.id, message);
        },
      });
    },
    [loadSessions, setPendingFor, initStreamingFor, appendStreamingFor, clearStreamingFor, setErrorFor],
  );

  const runTurn = useCallback(
    async (content: string, kind: "message" | "ship30") => {
      // Lazy creation: activeSession is null both on a fresh "New chat" click
      // and on first load with no sessions at all — either way, nothing gets
      // created in the backend until there's actually a message to send.
      let session = activeSession;
      if (!session) {
        setDraftErrorText(null);
        try {
          const created = await api.createSession(undefined, pseudoUserId());
          session = { ...created, messages: [] };
          setActiveSession(session);
        } catch (err) {
          setDraftErrorText(err instanceof ApiError ? err.message : "Could not start a new chat.");
          return;
        }
      } else {
        setErrorFor(session.id, null);
      }

      // Optimistic user bubble so the UI feels responsive before the reply lands.
      const optimisticUser = {
        id: `optimistic-${Date.now()}`,
        role: "user" as const,
        content,
        provider: null,
        citations: [],
        created_at: new Date().toISOString(),
      };
      setActiveSession((prev) => (prev && prev.id === session!.id ? { ...prev, messages: [...prev.messages, optimisticUser] } : prev));

      // The backend names a session from its first message — refresh the
      // sidebar list once (after the turn lands) so the new title (and, for
      // a lazily-created session, its very presence in the sidebar) shows up
      // without a manual reload.
      const wasUntitled = session.title === null;

      if (kind === "ship30") await runShip30(session, content, wasUntitled);
      else await runMessage(session, content, wasUntitled);
    },
    [activeSession, runShip30, runMessage, setErrorFor],
  );

  const handleStop = useCallback(() => {
    // Fire-and-forget: the stream's own onDone/onDelta handlers (already
    // running) take care of clearing pending/streaming state and persisting
    // whatever was generated so far once the backend wraps the turn up —
    // nothing else to do here client-side.
    if (activeSession) api.stopMessage(activeSession.id).catch(() => {});
  }, [activeSession]);

  const degraded = health && health.status !== "ok";
  const activePendingLabel = activeSession ? (pendingBySession[activeSession.id] ?? null) : null;
  const activeStreamingText = activeSession ? (streamingBySession[activeSession.id] ?? null) : null;
  const activeErrorText = activeSession ? (errorBySession[activeSession.id] ?? null) : draftErrorText;
  // A chat with a generation in flight, wherever you're currently looking —
  // lets the sidebar mark it so a background reply isn't invisible just
  // because you navigated away from it.
  const generatingSessionIds = new Set([...Object.keys(pendingBySession), ...Object.keys(streamingBySession)]);

  return (
    <div className="flex h-screen flex-col bg-slate-50 dark:bg-slate-950">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-400 dark:hover:bg-slate-800 md:hidden"
            onClick={() => setSidebarOpen((o) => !o)}
            aria-label="Toggle sessions"
          >
            <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5" aria-hidden>
              <path d="M3 5.5h14M3 10h14M3 14.5h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-brand-400 to-brand-600 text-xs font-bold text-white">
            L
          </div>
          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">Lenny Growth Assistant</span>
          {degraded && (
            <span
              title={[health?.db, health?.ollama, health?.anthropic]
                .filter((c) => c && c.status !== "ok")
                .map((c) => c?.detail)
                .filter(Boolean)
                .join(" · ")}
              className="hidden items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/50 dark:text-amber-300 sm:inline-flex"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
              Degraded
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeSession && (
            <ProviderToggle
              current={activeSession.llm_provider}
              health={health}
              onChange={handleProviderChange}
              pending={providerPending}
            />
          )}
          <ThemeToggle theme={theme} onToggle={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {sidebarOpen && (
          <button
            type="button"
            className="fixed inset-0 z-10 bg-black/30 md:hidden"
            aria-label="Close sessions"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <div className={`${sidebarOpen ? "block" : "hidden"} fixed z-20 h-[calc(100%-49px)] md:relative md:z-auto md:block`}>
          <SessionSidebar
            sessions={sessions}
            activeId={activeSession?.id ?? null}
            generatingIds={generatingSessionIds}
            onSelect={openSession}
            onNew={handleNewSession}
            onDelete={handleDeleteSession}
          />
        </div>

        <main className="flex min-w-0 flex-1 flex-col bg-slate-50 dark:bg-slate-950">
          <MessageList
            messages={activeSession?.messages ?? []}
            pendingLabel={activePendingLabel}
            streamingText={activeStreamingText}
            errorText={activeErrorText}
            onSuggestion={(text) => runTurn(text, "message")}
            onOpenArtifact={setArtifact}
          />
          <MessageInput
            disabled={!!activePendingLabel || activeStreamingText !== null}
            value={draft}
            onValueChange={setDraft}
            onSend={(text) => runTurn(text, "message")}
            onShip30={(text) => runTurn(text, "ship30")}
            onStop={handleStop}
          />
        </main>

        {artifact && (
          <div className="fixed inset-0 z-20 flex flex-col bg-white animate-fade-in dark:bg-slate-900 md:static md:inset-auto md:flex-none md:w-[44%] md:bg-transparent dark:md:bg-transparent">
            <ArtifactViewer artifact={artifact} onClose={() => setArtifact(null)} />
          </div>
        )}
      </div>
    </div>
  );
}
