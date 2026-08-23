import { useState } from "react";

import type { Citation } from "../types";

export function CitationList({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);

  if (citations.length === 0) {
    return <p className="mt-1 text-xs italic text-slate-400">No transcript sources supported this answer.</p>;
  }

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-medium text-slate-500 underline decoration-dotted hover:text-slate-700"
        aria-expanded={open}
      >
        Sources ({citations.length})
      </button>
      {open && (
        <ul className="mt-1 space-y-1 border-l-2 border-slate-200 pl-3">
          {citations.map((c) => (
            <li key={c.chunk_id} className="text-xs text-slate-600">
              <span className="font-medium">{c.title}</span>
              {c.guest && <span> — {c.guest}</span>}
              <span className="text-slate-400"> (relevance {c.score.toFixed(2)})</span>
              {c.url && (
                <>
                  {" · "}
                  <a href={c.url} target="_blank" rel="noreferrer" className="underline">
                    listen
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
