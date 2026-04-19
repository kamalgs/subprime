import { marked } from "marked";
import DOMPurify from "dompurify";
import { useMemo } from "react";

// Configure marked once. GitHub-flavoured markdown, auto-linkify, hard line
// breaks so the LLM's \n are honoured without requiring double-newline paras.
marked.setOptions({ gfm: true, breaks: true });

/** Render a blob of LLM-produced text as safe HTML: headings, bullets, bold,
 *  links. Text is parsed as markdown, then sanitised with DOMPurify so prompt
 *  injection cannot emit raw <script> or event handlers. */
export default function Prose({
  text,
  className = "",
}: { text: string; className?: string }) {
  // Two-stage pipeline: marked → DOMPurify. DOMPurify's default config
  // strips scripts, on* handlers, data: URLs, and other XSS vectors.
  const safeHtml = useMemo(() => {
    if (!text) return "";
    const rendered = marked.parse(text, { async: false }) as string;
    return DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
  }, [text]);

  if (!text) return null;
  // eslint-disable-next-line react/no-danger -- safeHtml is DOMPurify-sanitised above
  return <div className={"prose-compact " + className} dangerouslySetInnerHTML={{ __html: safeHtml }} />;
}
