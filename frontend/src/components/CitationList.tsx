import { useState } from "react";

import type { Citation } from "../types";

export function CitationList({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);

  if (citations.length === 0) {
    return (
      <p className="mt-1.5 flex items-center gap-1 text-xs italic text-slate-400 dark:text-slate-500">
        No transcript sources supported this answer
      </p>
    );
  }

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300 dark:hover:bg-slate-800"
        aria-expanded={open}
        aria-label={`${open ? "Hide" : "Show"} ${citations.length} source${citations.length === 1 ? "" : "s"}`}
      >
        <svg viewBox="0 0 16 16" fill="none" className="h-3 w-3" aria-hidden>
          <path
            d="M6 3h7v10H6M3 3h1v10H3M6 6h5M6 8.5h5M6 11h3"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
        </svg>
        {citations.length} source{citations.length === 1 ? "" : "s"}
        <svg
          viewBox="0 0 12 12"
          fill="none"
          className={`h-2.5 w-2.5 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          <path d="M2.5 4.5L6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1.5 border-l-2 border-slate-200 pl-3 dark:border-slate-700">
          {citations.map((c) => (
            <li key={c.chunk_id} className="text-xs text-slate-600 dark:text-slate-400">
              <span className="font-medium text-slate-800 dark:text-slate-200">{c.title}</span>
              {c.guest && <span> — {c.guest}</span>}
              <span className="text-slate-400 dark:text-slate-500"> · relevance {c.score.toFixed(2)}</span>
              {c.url && (
                <>
                  {" · "}
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand-700 underline decoration-dotted hover:text-brand-800 dark:text-brand-400 dark:hover:text-brand-300"
                  >
                    listen ↗
                  </a>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
