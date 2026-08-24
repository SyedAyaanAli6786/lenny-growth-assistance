import type { HealthResponse, Provider } from "../types";

interface Props {
  current: Provider;
  health: HealthResponse | null;
  onChange: (provider: Provider) => void;
  pending: boolean;
}

export function ProviderToggle({ current, health, onChange, pending }: Props) {
  const anthropicOk = health?.anthropic.status === "ok";
  const ollamaOk = health?.ollama.status === "ok";

  return (
    <div className="inline-flex overflow-hidden rounded-full border border-slate-300 text-xs font-medium dark:border-slate-700">
      {(
        [
          { key: "anthropic" as const, label: "Claude (cloud)", available: anthropicOk },
          { key: "ollama" as const, label: "Ollama (local)", available: ollamaOk },
        ]
      ).map(({ key, label, available }) => {
        const isActive = current === key;
        const disabled = pending || (!available && health !== null);
        const title = available || health === null ? undefined : health[key].detail || `${label} unavailable`;

        return (
          <button
            key={key}
            type="button"
            disabled={disabled}
            title={title}
            onClick={() => onChange(key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors ${
              isActive
                ? "bg-brand-600 text-white"
                : "bg-white text-slate-600 hover:bg-slate-50 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            } ${disabled && !isActive ? "cursor-not-allowed opacity-40" : ""}`}
          >
            <span
              aria-hidden
              className={`h-1.5 w-1.5 rounded-full ${available ? "bg-emerald-400" : "bg-rose-400"}`}
            />
            {label}
          </button>
        );
      })}
    </div>
  );
}
