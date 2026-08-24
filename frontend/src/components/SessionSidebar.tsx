import type { SessionSummary } from "../types";

interface Props {
  sessions: SessionSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function SessionSidebar({ sessions, activeId, onSelect, onNew }: Props) {
  return (
    <nav
      className="flex h-full w-64 flex-col border-r border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-900/60"
      aria-label="Sessions"
    >
      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-brand-600 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700"
        >
          <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5" aria-hidden>
            <path d="M8 2.5v11M2.5 8h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          New chat
        </button>
      </div>

      <p className="px-4 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        Recent
      </p>

      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {sessions.length === 0 && (
          <li className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">No sessions yet</li>
        )}
        {sessions.map((s) => {
          const isActive = s.id === activeId;
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                aria-current={isActive}
                className={`flex w-full flex-col rounded-xl px-3 py-2 text-left transition-colors ${
                  isActive
                    ? "bg-white shadow-sm ring-1 ring-slate-200 dark:bg-slate-800 dark:ring-slate-700"
                    : "hover:bg-white/70 dark:hover:bg-slate-800/60"
                }`}
              >
                <span
                  className={`truncate text-sm ${
                    isActive
                      ? "font-medium text-slate-900 dark:text-slate-100"
                      : "text-slate-600 dark:text-slate-300"
                  }`}
                >
                  {s.title || "Untitled session"}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                  {relativeTime(s.updated_at)}
                  <span aria-hidden>·</span>
                  <span className="uppercase tracking-wide">{s.llm_provider}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
