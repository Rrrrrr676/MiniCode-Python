import { useMemo, useState } from "react";

interface TextSegment {
  type: "text";
  text: string;
}

interface CodeSegment {
  type: "code";
  language: string;
  code: string;
}

type MarkdownSegment = TextSegment | CodeSegment;

function parseMarkdown(content: string): MarkdownSegment[] {
  const lines = content.split("\n");
  const segments: MarkdownSegment[] = [];
  let textBuffer: string[] = [];
  let codeBuffer: string[] | null = null;
  let language = "";

  function flushText() {
    if (textBuffer.length > 0) {
      segments.push({ type: "text", text: textBuffer.join("\n") });
      textBuffer = [];
    }
  }

  function flushCode() {
    if (codeBuffer) {
      segments.push({ type: "code", language, code: codeBuffer.join("\n") });
      codeBuffer = null;
      language = "";
    }
  }

  for (const line of lines) {
    const fence = line.match(/^```([A-Za-z0-9_+.-]*)\s*$/);
    if (fence) {
      if (codeBuffer) {
        flushCode();
      } else {
        flushText();
        codeBuffer = [];
        language = fence[1] || "text";
      }
      continue;
    }
    if (codeBuffer) codeBuffer.push(line);
    else textBuffer.push(line);
  }

  flushCode();
  flushText();
  return segments;
}

function safeHref(raw: string) {
  try {
    const url = new URL(raw, window.location.href);
    if (["http:", "https:", "mailto:"].includes(url.protocol)) return url.href;
  } catch {
    return "";
  }
  return "";
}

function InlineText({ text }: { text: string }) {
  const parts: Array<string | { label: string; href: string }> = [];
  const linkPattern = /\[([^\]]+)\]\(([^)\s]+)\)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = linkPattern.exec(text))) {
    if (match.index > cursor) parts.push(text.slice(cursor, match.index));
    const href = safeHref(match[2]);
    parts.push(href ? { label: match[1], href } : match[0]);
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));

  return (
    <>
      {parts.map((part, index) => (
        typeof part === "string" ? (
          <span key={index}>{part}</span>
        ) : (
          <a key={index} href={part.href} target="_blank" rel="noreferrer noopener">
            {part.label}
          </a>
        )
      ))}
    </>
  );
}

function CodeBlock({ language, code }: CodeSegment) {
  const [copied, setCopied] = useState(false);
  const lineCount = code ? code.split("\n").length : 0;
  const isLong = lineCount > 24 || code.length > 4_000;

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  const block = (
    <div className="code-block">
      <div className="code-toolbar">
        <span>{language || "text"}</span>
        <button type="button" className="quiet-button" onClick={() => void copyCode()}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );

  if (!isLong) return block;
  return (
    <details className="code-collapse">
      <summary>{language || "code"} · {lineCount} lines</summary>
      {block}
    </details>
  );
}

export function MarkdownMessage({ content }: { content: string }) {
  const segments = useMemo(() => parseMarkdown(content), [content]);

  return (
    <div className="markdown-body">
      {segments.map((segment, index) => (
        segment.type === "code" ? (
          <CodeBlock key={index} {...segment} />
        ) : (
          <p key={index}><InlineText text={segment.text} /></p>
        )
      ))}
    </div>
  );
}
