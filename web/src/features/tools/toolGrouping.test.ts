import { describe, expect, it } from "vitest";
import type { TimelineItem, ToolActivity } from "../../api/types";
import { groupTimelineTools } from "./toolGrouping";

function tool(id: string, name = "read_file", status: ToolActivity["status"] = "success"): ToolActivity {
  return { toolId: id, name, status, inputSummary: id, outputSummary: "done", durationMs: 2, turnId: "turn-1", startedSeq: Number(id) };
}

function item(id: string, seq: number, turnId = "turn-1"): TimelineItem {
  return { id: `tool-${id}`, kind: "tool", toolId: id, seq, turnId };
}

describe("groupTimelineTools", () => {
  it("collapses thirteen adjacent completed calls without changing their order", () => {
    const tools = Object.fromEntries(Array.from({ length: 13 }, (_, index) => [String(index + 1), tool(String(index + 1))]));
    const timeline = Array.from({ length: 13 }, (_, index) => item(String(index + 1), index + 1));

    const grouped = groupTimelineTools(timeline, tools);

    expect(grouped).toHaveLength(1);
    expect(grouped[0]).toMatchObject({ kind: "tool-group", toolIds: timeline.map((entry) => entry.kind === "tool" ? entry.toolId : "") });
  });

  it("keeps failures visible in a group and stops at messages or a new turn", () => {
    const tools = { one: tool("one"), two: tool("two", "read_file", "failed"), three: tool("three"), four: tool("four") };
    const message: TimelineItem = { id: "answer", kind: "message", role: "assistant", content: "answer", seq: 3, turnId: "turn-1" };
    const timeline = [item("one", 1), item("two", 2), message, item("three", 4), item("four", 5, "turn-2")];

    const grouped = groupTimelineTools(timeline, tools);

    expect(grouped.map((entry) => entry.kind)).toEqual(["tool-group", "message", "tool", "tool"]);
    expect(grouped[0]).toMatchObject({ toolIds: ["one", "two"] });
  });

  it("leaves running tools expanded as live individual cards", () => {
    const tools = { one: tool("one", "read_file", "running"), two: tool("two") };
    expect(groupTimelineTools([item("one", 1), item("two", 2)], tools).map((entry) => entry.kind)).toEqual(["tool", "tool"]);
  });
});
