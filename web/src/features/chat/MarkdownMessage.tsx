import {
  Children,
  Component,
  type ErrorInfo,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import { unified } from "unified";
import { visit } from "unist-util-visit";

interface MarkdownMessageProps {
  content: string;
  idPrefix?: string;
}

interface HeadingInfo {
  depth: number;
  id: string;
  text: string;
}

interface MarkdownAnalysis {
  headings: HeadingInfo[];
  outline: HeadingInfo[];
}

interface AstNode {
  type?: string;
  value?: string;
  depth?: number;
  children?: AstNode[];
  data?: { hProperties?: Record<string, unknown> };
}

const SAFE_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);

function nodeText(node: AstNode): string {
  if (typeof node.value === "string") return node.value;
  return node.children?.map(nodeText).join("") ?? "";
}

function slugify(value: string): string {
  const normalized = value
    .trim()
    .toLocaleLowerCase()
    .replace(/[^\p{Letter}\p{Number}\s-]/gu, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || "section";
}

function headingIds(tree: AstNode, prefix: string): HeadingInfo[] {
  const counts = new Map<string, number>();
  const headings: HeadingInfo[] = [];
  visit(tree as never, "heading", (node: AstNode) => {
    const text = nodeText(node).trim() || "Untitled section";
    const base = slugify(text);
    const count = (counts.get(base) ?? 0) + 1;
    counts.set(base, count);
    const id = `${prefix}-${base}${count > 1 ? `-${count}` : ""}`;
    node.data = node.data ?? {};
    node.data.hProperties = { ...node.data.hProperties, id };
    headings.push({ depth: node.depth ?? 2, id, text });
  });
  return headings;
}

function analyzeMarkdown(content: string, prefix: string): MarkdownAnalysis {
  try {
    const tree = unified().use(remarkParse).use(remarkGfm).parse(content) as AstNode;
    const headings = headingIds(tree, prefix);
    return { headings, outline: headings.filter((heading) => heading.depth === 2 || heading.depth === 3) };
  } catch {
    return { headings: [], outline: [] };
  }
}

function stableHeadingPlugin(options: { prefix: string }) {
  return (tree: AstNode) => {
    headingIds(tree, options.prefix);
  };
}

export function safeMarkdownUrl(raw: string): string {
  if (raw.startsWith("#")) return raw;
  try {
    const url = new URL(raw, window.location.href);
    return SAFE_PROTOCOLS.has(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function isExternalLink(href: string): boolean {
  try {
    const url = new URL(href, window.location.href);
    return (url.protocol === "http:" || url.protocol === "https:") && url.origin !== window.location.origin;
  } catch {
    return false;
  }
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<number | undefined>(undefined);
  const lineCount = code.length ? code.split("\n").length : 0;
  const isLong = lineCount > 24 || code.length > 4_000;

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setCopied(false), 1_400);
    } catch {
      setCopied(false);
    }
  }

  const block = (
    <div className="code-block">
      <div className="code-toolbar">
        {language ? <span>{language}</span> : <span aria-hidden="true" />}
        <button
          type="button"
          className="code-copy"
          aria-label={copied ? "Code copied" : "Copy code"}
          title={copied ? "Copied" : "Copy code"}
          onClick={() => void copyCode()}
        >
          <span aria-hidden="true">{copied ? "✓" : "⧉"}</span>
        </button>
        <span className="copy-status" role="status" aria-live="polite">{copied ? "Copied" : ""}</span>
      </div>
      <pre tabIndex={0}><code>{code}</code></pre>
    </div>
  );

  if (!isLong) return block;
  return (
    <details className="code-collapse">
      <summary aria-label={`${language || "Plain text"} code block, ${lineCount} lines`}>
        <span>{language || "Plain text"}</span><span>{lineCount} lines</span>
      </summary>
      {block}
    </details>
  );
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(
    "a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])",
  )).filter((element) => element.offsetParent !== null);
}

function MessageOutline({ headings }: { headings: HeadingInfo[] }) {
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState(headings[0]?.id ?? "");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const firstHeading = document.getElementById(headings[0]?.id ?? "");
    const transcript = firstHeading?.closest<HTMLElement>(".transcript");
    if (!transcript) return undefined;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const top = transcript.getBoundingClientRect().top + 110;
        let next = headings[0]?.id ?? "";
        for (const heading of headings) {
          const element = document.getElementById(heading.id);
          if (element && element.getBoundingClientRect().top <= top) next = heading.id;
        }
        setActiveId((current) => current === next ? current : next);
      });
    };
    transcript.addEventListener("scroll", update, { passive: true });
    update();
    return () => {
      cancelAnimationFrame(frame);
      transcript.removeEventListener("scroll", update);
    };
  }, [headings]);

  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    panel?.querySelector<HTMLElement>("button")?.focus();
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        requestAnimationFrame(() => triggerRef.current?.focus());
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = focusableElements(panel);
      if (!items.length) return;
      const first = items[0];
      const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  function jumpTo(id: string) {
    const heading = document.getElementById(id);
    const transcript = heading?.closest<HTMLElement>(".transcript");
    if (!heading || !transcript) return;
    const rootTop = transcript.getBoundingClientRect().top;
    const targetTop = transcript.scrollTop + heading.getBoundingClientRect().top - rootTop - 20;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    transcript.scrollTo({ top: targetTop, behavior: reducedMotion ? "auto" : "smooth" });
    setActiveId(id);
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  }

  function keepDialogOpen(event: ReactKeyboardEvent) {
    event.stopPropagation();
  }

  return (
    <div className="message-outline">
      <button
        ref={triggerRef}
        type="button"
        className="outline-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        Contents <span aria-hidden="true">{open ? "↑" : "↓"}</span>
      </button>
      {open && (
        <div
          ref={panelRef}
          className="outline-panel"
          role="dialog"
          aria-modal="true"
          aria-label="Answer contents"
          onKeyDown={keepDialogOpen}
        >
          <div className="outline-heading"><strong>Contents</strong><button type="button" aria-label="Close contents" onClick={() => { setOpen(false); triggerRef.current?.focus(); }}>×</button></div>
          <ol>
            {headings.map((heading) => (
              <li key={heading.id} className={`outline-level-${heading.depth}`}>
                <button
                  type="button"
                  aria-current={activeId === heading.id ? "location" : undefined}
                  onClick={() => jumpTo(heading.id)}
                >
                  {heading.text}
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

class MarkdownErrorBoundary extends Component<
  { content: string; children: ReactNode },
  { failedContent: string | null }
> {
  state = { failedContent: null as string | null };

  static getDerivedStateFromError() {
    return { failedContent: "failed" };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // The safe text fallback below deliberately avoids logging user content.
  }

  componentDidUpdate(previous: { content: string }) {
    if (previous.content !== this.props.content && this.state.failedContent !== null) {
      this.setState({ failedContent: null });
    }
  }

  render() {
    if (this.state.failedContent !== null) {
      return <p className="markdown-fallback">{this.props.content}</p>;
    }
    return this.props.children;
  }
}

export function MarkdownMessage({ content, idPrefix = "answer" }: MarkdownMessageProps) {
  const prefix = useMemo(() => `md-${slugify(idPrefix)}`, [idPrefix]);
  const analysis = useMemo(() => analyzeMarkdown(content, prefix), [content, prefix]);
  const showOutline = analysis.outline.length > 0 && (analysis.headings.length >= 4 || content.length > 3_000);
  const plugins = useMemo(() => [remarkGfm, [stableHeadingPlugin, { prefix }]] as never, [prefix]);

  return (
    <MarkdownErrorBoundary content={content}>
      <div className="markdown-message">
        {showOutline && <MessageOutline headings={analysis.outline} />}
        <div className="markdown-body">
          <ReactMarkdown
            remarkPlugins={plugins}
            urlTransform={safeMarkdownUrl}
            components={{
              a: ({ node: _node, href = "", children, ...props }) => {
                const external = isExternalLink(href);
                return <a {...props} href={href} target={external ? "_blank" : undefined} rel={external ? "noreferrer noopener" : undefined}>{children}</a>;
              },
              pre: ({ children }) => <>{children}</>,
              code: ({ node: _node, className = "", children, ...props }) => {
                const raw = Children.toArray(children).join("");
                const language = /language-([^\s]+)/.exec(className)?.[1] ?? "";
                const fenced = Boolean(language) || raw.endsWith("\n");
                if (!fenced) return <code {...props} className={className}>{children}</code>;
                return <CodeBlock language={language} code={raw.replace(/\n$/, "")} />;
              },
              table: ({ node: _node, children, ...props }) => <div className="table-scroll" tabIndex={0}><table {...props}>{children}</table></div>,
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </MarkdownErrorBoundary>
  );
}
