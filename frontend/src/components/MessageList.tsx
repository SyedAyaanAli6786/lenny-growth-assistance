import { useEffect, useRef } from "react";

import type { MessageData } from "../types";
import { CitationList } from "./CitationList";

interface Props {
  messages: MessageData[];
  pendingLabel: string | null;
  errorText: string | null;
}

export function MessageList({ messages, pendingLabel, errorText }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, pendingLabel, errorText]);

  if (messages.length === 0 && !pendingLabel && !errorText) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center text-slate-400">
        <p className="mb-3 text-sm font-medium text-slate-500">Ask about product, growth, retention…</p>
        <ul className="space-y-1 text-xs">
          <li>&ldquo;How should I think about activation for a PLG product?&rdquo;</li>
          <li>&ldquo;What do Lenny&apos;s guests say about pricing experiments?&rdquo;</li>
          <li>&ldquo;Turn that into a Ship 30 for 30 essay.&rdquo;</li>
        </ul>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4" aria-live="polite" role="log">
      <ul className="mx-auto flex max-w-2xl flex-col gap-4">
        {messages.map((m) => (
          <li key={m.id} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
                m.role === "user" ? "bg-slate-900 text-white" : "bg-white text-slate-900 shadow-sm"
              }`}
            >
              {m.content}
            </div>
            {m.role === "assistant" && (
              <div className="mt-0.5 flex max-w-[85%] items-center gap-2 px-1">
                {m.provider && <span className="text-[10px] uppercase tracking-wide text-slate-400">{m.provider}</span>}
                <CitationList citations={m.citations} />
              </div>
            )}
          </li>
        ))}

        {pendingLabel && (
          <li className="flex items-start">
            <div className="max-w-[85%] rounded-2xl bg-white px-4 py-2 text-sm text-slate-400 shadow-sm">
              {pendingLabel}
            </div>
          </li>
        )}

        {errorText && (
          <li className="flex items-start" role="alert">
            <div className="max-w-[85%] rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
              {errorText}
            </div>
          </li>
        )}
      </ul>
      <div ref={bottomRef} />
    </div>
  );
}
