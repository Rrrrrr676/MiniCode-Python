// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ToolActivity } from "../../api/types";
import { ToolGroup } from "./ToolGroup";

afterEach(cleanup);

function tool(toolId: string, status: ToolActivity["status"], durationMs: number): ToolActivity {
  return {
    toolId,
    name: "read_file",
    status,
    inputSummary: `${toolId}.txt`,
    outputSummary: status === "failed" ? "could not read" : "contents",
    durationMs,
  };
}

describe("ToolGroup", () => {
  it("announces totals and exposes every original call when expanded", () => {
    const { container } = render(<ToolGroup tools={[tool("one", "success", 12), tool("two", "failed", 22)]} />);
    const details = container.querySelector("details")!;
    const summary = container.querySelector("summary")!;

    expect(details).not.toHaveAttribute("open");
    expect(summary).toHaveAccessibleName("Read 2 files. 1 succeeded, 1 failed. 34 milliseconds");
    fireEvent.click(summary);
    expect(details).toHaveAttribute("open");
    expect(screen.getByText("one.txt")).toBeInTheDocument();
    expect(screen.getByText("two.txt")).toBeInTheDocument();
  });
});
