import { useState } from "react";

interface Props {
  disabled: boolean;
  onSend: (text: string) => void;
  onShip30: (text: string) => void;
}

export function MessageInput({ disabled, onSend, onShip30 }: Props) {
  const [value, setValue] = useState("");

  const submit = (handler: (text: string) => void) => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    handler(trimmed);
    setValue("");
  };

  return (
    <form
      className="flex items-end gap-2 border-t border-slate-200 bg-white px-4 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit(onSend);
      }}
    >
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit(onSend);
          }
        }}
        rows={1}
        placeholder="Ask a product or growth question…"
        disabled={disabled}
        className="max-h-32 flex-1 resize-none rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none disabled:bg-slate-50"
        aria-label="Message"
      />
      <button
        type="button"
        disabled={disabled || !value.trim()}
        onClick={() => submit(onShip30)}
        title="Turn this into a Ship 30 for 30 essay"
        className="rounded-xl border border-slate-300 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
      >
        Ship 30/30
      </button>
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
      >
        Send
      </button>
    </form>
  );
}
