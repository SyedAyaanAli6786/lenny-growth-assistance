import { useEffect, useRef, useState } from "react";

import { renderMarkdown } from "../lib/markdown";
import type { ArtifactData, MessageData } from "../types";
import { CitationList } from "./CitationList";

interface Props {
  messages: MessageData[];
  pendingLabel: string | null;
  streamingText: string | null;
  errorText: string | null;
  onSuggestion: (text: string) => void;
  onOpenArtifact: (artifact: ArtifactData) => void;
}

const ASSISTANT_BUBBLE_CLASS =
  "prose prose-sm max-w-none rounded-2xl rounded-tl-sm bg-white px-4 py-2.5 text-slate-900 shadow-sm ring-1 ring-slate-200 prose-p:my-1.5 prose-headings:my-2 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 first:prose-p:mt-0 last:prose-p:mb-0 dark:bg-slate-800 dark:text-slate-100 dark:ring-slate-700 dark:prose-invert";

const SUGGESTIONS = [
  "How should I think about activation for a PLG product?",
  "What do Lenny's guests say about pricing experiments?",
  "What separates good onboarding from great onboarding?",
];

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function AssistantAvatar() {
  return (
    <div
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-xs font-semibold text-white shadow-sm"
      aria-hidden
    >
      L
    </div>
  );
}

function UserAvatar() {
  return (
    <div
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-white dark:bg-slate-600"
      aria-hidden
    >
      You
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {
          // clipboard can be unavailable; button just won't flip state
        }
      }}
      className="rounded p-1 text-slate-400 opacity-0 transition-opacity hover:bg-slate-100 hover:text-slate-600 focus-visible:opacity-100 group-hover:opacity-100 dark:hover:bg-slate-800 dark:hover:text-slate-300"
      aria-label="Copy message"
    >
      {copied ? (
        <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5" aria-hidden>
          <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : (
        <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5" aria-hidden>
          <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M3 10.5V3.5A1 1 0 014 2.5h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )}
    </button>
  );
}

function TypingIndicator({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm bg-white px-4 py-3 text-sm text-slate-500 shadow-sm ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700">
      <span className="flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-slate-400 [animation-delay:-0.3s] dark:bg-slate-500" />
        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-slate-400 [animation-delay:-0.15s] dark:bg-slate-500" />
        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-slate-400 dark:bg-slate-500" />
      </span>
      <span>{label}</span>
    </div>
  );
}

export function MessageList({ messages, pendingLabel, streamingText, errorText, onSuggestion, onOpenArtifact }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Whether the user is (still) at the bottom of the scroll area — read on
  // every scroll event, not just once, so scrolling away mid-stream is
  // noticed immediately rather than only at the next render.
  const isNearBottomRef = useRef(true);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  // A new message (the user's own send, or a reply that just finished)
  // always snaps to the bottom — that's an explicit action or a turn
  // completing, not something to fight the user's scroll position over.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    isNearBottomRef.current = true;
  }, [messages.length]);

  // Token-by-token streaming growth, by contrast, only follows the bottom if
  // the user hasn't scrolled away to read something else. Previously this
  // ran unconditionally on every delta, which yanked the view back down on
  // every token and made it impossible to scroll up while a reply streamed
  // in. "auto" (instant), not "smooth" — a smooth scroll re-triggered many
  // times a second just fights itself.
  useEffect(() => {
    if (isNearBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
    }
  }, [streamingText, pendingLabel, errorText]);

  if (messages.length === 0 && !pendingLabel && !streamingText && !errorText) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-400 to-brand-600 text-lg font-semibold text-white shadow-sm">
          L
        </div>
        <p className="mb-1 text-base font-semibold text-slate-700 dark:text-slate-200">Lenny Growth Assistant</p>
        <p className="mb-5 max-w-sm text-sm text-slate-400 dark:text-slate-500">
          Ask a product or growth question. Every answer is grounded in Lenny&apos;s Podcast transcripts, with
          sources you can check.
        </p>
        <div className="flex w-full max-w-md flex-col gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSuggestion(s)}
              className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-left text-sm text-slate-600 shadow-sm transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-brand-700 dark:hover:bg-slate-800/70 dark:hover:text-slate-100"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 py-4"
      aria-live="polite"
      aria-atomic="false"
      role="log"
    >
      <ul className="mx-auto flex max-w-2xl flex-col gap-5">
        {messages.map((m) => {
          const isUser = m.role === "user";
          return (
            <li key={m.id} className={`group flex items-start gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}>
              {isUser ? <UserAvatar /> : <AssistantAvatar />}
              <div className={`flex min-w-0 max-w-[85%] flex-col ${isUser ? "items-end" : "items-start"}`}>
                {isUser ? (
                  <div className="whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white shadow-sm">
                    {m.content}
                  </div>
                ) : m.artifact ? (
                  <button
                    type="button"
                    onClick={() => onOpenArtifact(m.artifact!)}
                    title="Reopen artifact"
                    className={`${ASSISTANT_BUBBLE_CLASS} cursor-pointer text-left transition-colors hover:ring-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:ring-brand-700`}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }}
                  />
                ) : m.content.trim() ? (
                  <div className={ASSISTANT_BUBBLE_CLASS} dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
                ) : (
                  // Generation can be stopped before the model produced any
                  // token at all — an empty bubble here would look broken
                  // rather than intentional.
                  <div className={`${ASSISTANT_BUBBLE_CLASS} italic text-slate-400 dark:text-slate-500`}>
                    Stopped before any response was generated.
                  </div>
                )}

                <div
                  className={`mt-1 flex items-center gap-2 px-1 text-[11px] text-slate-400 dark:text-slate-500 ${
                    isUser ? "flex-row-reverse" : ""
                  }`}
                >
                  <span>{formatTime(m.created_at)}</span>
                  {!isUser && m.provider && <span className="uppercase tracking-wide">{m.provider}</span>}
                  {!isUser && <CopyButton text={m.content} />}
                </div>

                {!isUser && <CitationList citations={m.citations} />}
              </div>
            </li>
          );
        })}

        {pendingLabel && (
          <li className="flex items-start gap-2.5">
            <AssistantAvatar />
            <TypingIndicator label={pendingLabel} />
          </li>
        )}

        {streamingText !== null && (
          <li className="flex items-start gap-2.5 animate-fade-in">
            <AssistantAvatar />
            <div className="flex min-w-0 max-w-[85%] flex-col items-start">
              <div className={ASSISTANT_BUBBLE_CLASS} dangerouslySetInnerHTML={{ __html: renderMarkdown(streamingText) }} />
            </div>
          </li>
        )}

        {errorText && (
          <li className="flex items-start gap-2.5 animate-fade-in" role="alert">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-rose-100 font-semibold text-rose-600 dark:bg-rose-900/60 dark:text-rose-300">
              !
            </div>
            <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300">
              {errorText}
            </div>
          </li>
        )}
      </ul>
      <div ref={bottomRef} />
    </div>
  );
}
