import type { ToolActivity } from "../../api/types";

export function ToolCard({ tool, compact = false }: { tool: ToolActivity; compact?: boolean }) {
  const symbol = tool.status === "running" ? "◌" : tool.status === "success" ? "✓" : "!";
  return (
    <details className={`tool-card tool-${tool.status} ${compact ? "tool-card-compact" : ""}`}>
      <summary aria-label={`${tool.name}, ${tool.status}${tool.durationMs !== null ? `, ${Math.round(tool.durationMs)} milliseconds` : ""}`}>
        <span aria-hidden="true">{symbol}</span>
        <strong>{tool.name}</strong>
        <span>{tool.status}</span>
        {tool.durationMs !== null && <time>{Math.round(tool.durationMs)} ms</time>}
      </summary>
      {tool.inputSummary && <pre>{tool.inputSummary}</pre>}
      {tool.outputSummary && <pre>{tool.outputSummary}</pre>}
    </details>
  );
}
