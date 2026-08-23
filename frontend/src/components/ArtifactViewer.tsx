import DOMPurify from "dompurify";
import { marked } from "marked";
import { useMemo, useRef, useState } from "react";

import type { ArtifactData } from "../types";

// Untrusted-HTML isolation policy (see architecture.md "Security: artifact rendering"):
//   - srcdoc gives the frame a unique opaque origin (no allow-same-origin)
//   - sandbox="allow-scripts" only: no top navigation, no forms, no popups,
//     no parent-DOM access, no cookies/localStorage/same-origin fetches
//   - an injected strict CSP blocks outbound network calls from inside the frame
const ARTIFACT_CSP =
  "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'\">";

function renderMarkdown(content: string): string {
  // marked with default options never re-parses raw inline HTML as elements,
  // and DOMPurify strips any residual markup as defense in depth — the
  // artifact preview never gets an HTML escape hatch.
  const html = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(html);
}

function wrapHtmlArtifact(content: string): string {
  if (/<head[\s>]/i.test(content)) {
    return content.replace(/<head[^>]*>/i, (match) => `${match}${ARTIFACT_CSP}`);
  }
  return `<!doctype html><html><head>${ARTIFACT_CSP}</head><body>${content}</body></html>`;
}

export function ArtifactViewer({ artifact, onClose }: { artifact: ArtifactData; onClose: () => void }) {
  const [tab, setTab] = useState<"preview" | "source">("preview");
  const headingRef = useRef<HTMLHeadingElement>(null);

  const renderedMarkdown = useMemo(
    () => (artifact.type === "markdown" ? renderMarkdown(artifact.content) : ""),
    [artifact],
  );
  const wrappedHtml = useMemo(
    () => (artifact.type === "html" ? wrapHtmlArtifact(artifact.content) : ""),
    [artifact],
  );

  return (
    <aside
      className="flex h-full w-full flex-col border-l border-slate-200 bg-white md:w-[42%]"
      aria-label="Artifact viewer"
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 ref={headingRef} tabIndex={-1} className="truncate text-sm font-semibold">
          {artifact.title || (artifact.type === "html" ? "HTML artifact" : "Markdown artifact")}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
          aria-label="Close artifact viewer"
        >
          Close
        </button>
      </div>

      <div className="flex gap-1 border-b border-slate-200 px-3 pt-2">
        {(["preview", "source"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-t px-3 py-1.5 text-xs font-medium capitalize ${
              tab === t ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-700"
            }`}
            aria-current={tab === t}
          >
            {t}
          </button>
        ))}
      </div>

      {artifact.type === "html" && tab === "preview" && (
        <p className="border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-xs text-amber-800">
          Sandboxed preview — scripts run, but network access and parent-page access are blocked.
        </p>
      )}

      <div className="flex-1 overflow-auto">
        {tab === "source" && (
          <pre className="whitespace-pre-wrap break-words p-4 text-xs text-slate-700">{artifact.content}</pre>
        )}

        {tab === "preview" && artifact.type === "markdown" && (
          <div
            className="prose prose-sm max-w-none p-4"
            // Safe: renderMarkdown() runs marked (no raw-HTML passthrough) then DOMPurify.
            dangerouslySetInnerHTML={{ __html: renderedMarkdown }}
          />
        )}

        {tab === "preview" && artifact.type === "html" && (
          <iframe
            title={artifact.title || "HTML artifact preview"}
            className="h-full w-full"
            sandbox="allow-scripts"
            srcDoc={wrappedHtml}
          />
        )}
      </div>
    </aside>
  );
}
