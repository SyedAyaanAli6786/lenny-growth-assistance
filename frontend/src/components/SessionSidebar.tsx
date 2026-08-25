import { useState } from "react";

import type { SessionSummary } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

interface Props {
  sessions: SessionSummary[];
  activeId: string | null;
  generatingIds: Set<string>;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
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

export function SessionSidebar({ sessions, activeId, generatingIds, onSelect, onNew, onDelete }: Props) {
  const [deleteTarget, setDeleteTarget] = useState<SessionSummary | null>(null);

  return (
    <nav
      className="ml-3 flex h-full w-64 flex-col border-r border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-900/60"
      aria-label="Sessions"
    >
      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-brand-600 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1"
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
            <li key={s.id} className="group relative">
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                aria-current={isActive}
                className={`flex w-full flex-col rounded-xl px-3 py-2 pr-8 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1 ${
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
                  {s.title ? s.title : <span className="italic text-slate-400 dark:text-slate-500">Untitled session</span>}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                  {relativeTime(s.updated_at)}
                  <span aria-hidden>·</span>
                  <span className="uppercase tracking-wide">{s.llm_provider}</span>
                  {generatingIds.has(s.id) && (
                    // A reply can still be generating for a chat you've
                    // navigated away from — this is the only signal that
                    // it's happening, since the chat panel itself only shows
                    // progress for whichever session is currently open.
                    <span className="inline-flex items-center gap-1 text-brand-600 dark:text-brand-400">
                      <span aria-hidden>·</span>
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" aria-hidden />
                      generating
                    </span>
                  )}
                </span>
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteTarget(s);
                }}
                aria-label={`Delete ${s.title || "Untitled session"}`}
                // Hover-to-reveal only makes sense where hover is a real,
                // reliable input signal — a mouse on desktop. Touch devices
                // have no equivalent persistent "hovering" state, so
                // opacity-0 + group-hover would leave this permanently
                // invisible below the md breakpoint. Visible by default on
                // small screens; hidden-until-hover only from md up.
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 opacity-100 transition-opacity hover:bg-slate-200 hover:text-rose-600 focus-visible:opacity-100 md:opacity-0 md:group-hover:opacity-100 dark:hover:bg-slate-700 dark:hover:text-rose-400"
              >
                <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5" aria-hidden>
                  <path
                    d="M3 4.5h10M6.5 4.5V3a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1.5M4.5 4.5v8a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1v-8"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </li>
          );
        })}
      </ul>

      {deleteTarget && (
        <ConfirmDialog
          title={`Delete "${deleteTarget.title || "Untitled session"}"?`}
          description="This permanently deletes the chat and all its messages. This can't be undone."
          confirmLabel="Delete"
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => {
            onDelete(deleteTarget.id);
            setDeleteTarget(null);
          }}
        />
      )}
    </nav>
  );
}
