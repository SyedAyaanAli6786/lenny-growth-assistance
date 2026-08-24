import { useEffect, useMemo, useRef, useState } from "react";

import { renderMarkdown } from "../lib/markdown";
import type { ArtifactData } from "../types";

// Untrusted-HTML isolation policy (see architecture.md "Security: artifact rendering"):
//   - srcdoc gives the frame a unique opaque origin (no allow-same-origin)
//   - sandbox="allow-scripts" only: no top navigation, no forms, no popups,
//     no parent-DOM access, no cookies/localStorage/same-origin fetches
//   - an injected strict CSP blocks outbound network calls from inside the frame
const ARTIFACT_CSP =
  "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'\">";

function wrapHtmlArtifact(content: string): string {
  if (/<head[\s>]/i.test(content)) {
    return content.replace(/<head[^>]*>/i, (match) => `${match}${ARTIFACT_CSP}`);
  }
  return `<!doctype html><html><head>${ARTIFACT_CSP}</head><body>${content}</body></html>`;
}

function fileExtensionFor(artifact: ArtifactData): string {
  return artifact.type === "html" ? "html" : "md";
}

export function ArtifactViewer({ artifact, onClose }: { artifact: ArtifactData; onClose: () => void }) {
  const [tab, setTab] = useState<"preview" | "source">("preview");
  const [copied, setCopied] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, [artifact]);

  useEffect(() => {
    setTab("preview");
    setCopied(false);
  }, [artifact]);

  const renderedMarkdown = useMemo(
    () => (artifact.type === "markdown" ? renderMarkdown(artifact.content) : ""),
    [artifact],
  );
  const wrappedHtml = useMemo(
    () => (artifact.type === "html" ? wrapHtmlArtifact(artifact.content) : ""),
    [artifact],
  );

  const copySource = async () => {
    try {
      await navigator.clipboard.writeText(artifact.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API can be unavailable (insecure context, permissions) —
      // failing silently here just means the button doesn't flip to "Copied".
    }
  };

  const downloadSource = () => {
    const blob = new Blob([artifact.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(artifact.title || "artifact").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.${fileExtensionFor(artifact)}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <aside
      className="flex h-full w-full flex-col border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 md:w-[44%]"
      aria-label="Artifact viewer"
    >
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-700 dark:bg-brand-900/50 dark:text-brand-300">
            {artifact.type === "html" ? "</>" : "≡"}
          </span>
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="truncate text-sm font-semibold text-slate-900 outline-none dark:text-slate-100"
          >
            {artifact.title || (artifact.type === "html" ? "HTML artifact" : "Markdown artifact")}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          aria-label="Close artifact viewer"
        >
          <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden>
            <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div className="flex items-center justify-between gap-1 border-b border-slate-200 px-3 pt-2 dark:border-slate-800">
        <div className="flex gap-1">
          {(["preview", "source"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`rounded-t-lg px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                tab === t
                  ? "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
              aria-current={tab === t}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="mb-1 flex gap-1">
          <button
            type="button"
            onClick={copySource}
            className="rounded-lg px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            type="button"
            onClick={downloadSource}
            className="rounded-lg px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            Download
          </button>
        </div>
      </div>

      {artifact.type === "html" && tab === "preview" && (
        <p className="border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
          Sandboxed preview — scripts run, but network access and parent-page access are blocked.
        </p>
      )}

      <div className="flex-1 overflow-auto bg-white dark:bg-slate-900">
        {tab === "source" && (
          <pre className="whitespace-pre-wrap break-words p-4 font-mono text-xs text-slate-700 dark:text-slate-300">
            {artifact.content}
          </pre>
        )}

        {tab === "preview" && artifact.type === "markdown" && (
          <div
            className="prose prose-sm max-w-none p-4 dark:prose-invert"
            // Safe: renderMarkdown() runs marked (no raw-HTML passthrough) then DOMPurify.
            dangerouslySetInnerHTML={{ __html: renderedMarkdown }}
          />
        )}

        {tab === "preview" && artifact.type === "html" && (
          <iframe
            title={artifact.title || "HTML artifact preview"}
            className="h-full w-full bg-white"
            sandbox="allow-scripts"
            srcDoc={wrappedHtml}
          />
        )}
      </div>
    </aside>
  );
}
