import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ breaks: true });

/**
 * Shared markdown -> sanitized HTML path for both chat bubbles and the
 * markdown artifact preview. marked's default config never re-parses raw
 * inline HTML as elements, and DOMPurify strips any residual markup as
 * defense in depth — model output never gets an HTML escape hatch here.
 */
export function renderMarkdown(content: string): string {
  const html = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(html);
}
