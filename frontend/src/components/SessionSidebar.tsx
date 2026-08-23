import type { SessionSummary } from "../types";

interface Props {
  sessions: SessionSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export function SessionSidebar({ sessions, activeId, onSelect, onNew }: Props) {
  return (
    <nav className="flex h-full w-60 flex-col border-r border-slate-200 bg-white" aria-label="Sessions">
      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          className="w-full rounded-lg border border-slate-300 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          + New chat
        </button>
      </div>
      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {sessions.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => onSelect(s.id)}
              aria-current={s.id === activeId}
              className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm ${
                s.id === activeId ? "bg-slate-100 font-medium text-slate-900" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {s.title || "Untitled session"}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
