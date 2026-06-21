import type { ToolActivity } from "../../api/types";

export function ToolCard({ tool }: { tool: ToolActivity }) {
  const symbol = tool.status === "running" ? "◌" : tool.status === "success" ? "✓" : "!";
  return (
    <details className={`tool-card tool-${tool.status}`}>
      <summary>
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
