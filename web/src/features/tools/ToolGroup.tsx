import type { ToolActivity } from "../../api/types";
import { ToolCard } from "./ToolCard";

function actionLabel(name: string, count: number) {
  const labels: Record<string, [string, string]> = {
    read_file: ["Read", "files"],
    write_file: ["Wrote", "files"],
    edit_file: ["Edited", "files"],
    list_directory: ["Listed", "directories"],
    run_command: ["Ran", "commands"],
  };
  const [verb, noun] = labels[name] ?? [name.replaceAll("_", " "), count === 1 ? "call" : "calls"];
  return `${verb} ${count} ${noun}`;
}

export function ToolGroup({ tools }: { tools: ToolActivity[] }) {
  const failed = tools.filter((tool) => tool.status === "failed").length;
  const success = tools.filter((tool) => tool.status === "success").length;
  const running = tools.length - failed - success;
  const duration = tools.reduce((total, tool) => total + (tool.durationMs ?? 0), 0);
  const status = running ? "running" : failed ? "failed" : "success";
  const label = actionLabel(tools[0]?.name ?? "tool", tools.length);
  const statusText = [
    `${success} succeeded`,
    failed ? `${failed} failed` : "",
    running ? `${running} running` : "",
  ].filter(Boolean).join(", ");

  return (
    <details className={`tool-group tool-${status}`}>
      <summary aria-label={`${label}. ${statusText}. ${Math.round(duration)} milliseconds`}>
        <span className="tool-group-symbol" aria-hidden="true">{failed ? "!" : running ? "◌" : "✓"}</span>
        <strong>{label}</strong>
        <span className="tool-group-counts">{statusText}</span>
        <time>{Math.round(duration)} ms</time>
      </summary>
      <div className="tool-group-items">
        {tools.map((tool, index) => (
          <div className="tool-group-item" key={tool.toolId}>
            <span className="tool-seq" aria-hidden="true">{index + 1}</span>
            <ToolCard tool={tool} compact />
          </div>
        ))}
      </div>
    </details>
  );
}
