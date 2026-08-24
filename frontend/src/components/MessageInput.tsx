import { useEffect, useRef, useState } from "react";

interface Props {
  disabled: boolean;
  value: string;
  onValueChange: (value: string) => void;
  onSend: (text: string) => void;
  onShip30: (text: string) => void;
}

const MAX_LENGTH = 8000;

export function MessageInput({ disabled, value, onValueChange, onSend, onShip30 }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const submit = (handler: (text: string) => void) => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    handler(trimmed);
    onValueChange("");
  };

  const nearLimit = value.length > MAX_LENGTH - 200;

  return (
    <form
      className="border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900"
      onSubmit={(e) => {
        e.preventDefault();
        submit(onSend);
      }}
    >
      <div
        className={`mx-auto flex max-w-2xl items-end gap-2 rounded-2xl border bg-white px-3 py-2 shadow-sm transition-colors dark:bg-slate-800 ${
          focused ? "border-brand-400 ring-2 ring-brand-100 dark:border-brand-600 dark:ring-brand-900/40" : "border-slate-300 dark:border-slate-700"
        }`}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onValueChange(e.target.value.slice(0, MAX_LENGTH))}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(onSend);
            }
          }}
          rows={1}
          placeholder="Ask a product or growth question…"
          disabled={disabled}
          className="max-h-[200px] flex-1 resize-none bg-transparent py-1 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none disabled:opacity-60 dark:text-slate-100 dark:placeholder:text-slate-500"
          aria-label="Message"
        />

        <button
          type="button"
          disabled={disabled || !value.trim()}
          onClick={() => submit(onShip30)}
          title="Turn this into a Ship 30 for 30 essay"
          className="flex shrink-0 items-center gap-1 rounded-xl border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5" aria-hidden>
            <path
              d="M2 8.5l5-5.5 7 5.5-7 5.5-5-5.5z"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinejoin="round"
            />
          </svg>
          <span className="hidden sm:inline">Ship 30/30</span>
        </button>

        <button
          type="submit"
          disabled={disabled || !value.trim()}
          aria-label="Send message"
          className="flex shrink-0 items-center justify-center rounded-xl bg-brand-600 p-2 text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden>
            <path
              d="M10 16V4M10 4l-5 5M10 4l5 5"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
      <div className="mx-auto mt-1.5 flex max-w-2xl items-center justify-between px-1 text-[11px] text-slate-400 dark:text-slate-500">
        <span>Enter to send · Shift+Enter for a new line</span>
        {nearLimit && (
          <span className={value.length >= MAX_LENGTH ? "text-rose-500" : ""}>
            {value.length}/{MAX_LENGTH}
          </span>
        )}
      </div>
    </form>
  );
}
