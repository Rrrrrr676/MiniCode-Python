import { describe, expect, it } from "vitest";
import type { WebEvent } from "../api/types";
import { initialSessionState, sessionReducer } from "./sessionStore";

function event(seq: number, type: WebEvent["type"], payload: Record<string, unknown>): WebEvent {
  return { seq, type, payload, sessionId: "session-1", turnId: "turn-1", timestamp: "2026-06-19T00:00:00Z" };
}

describe("sessionReducer", () => {
  it("merges assistant deltas in sequence", () => {
    let state = initialSessionState("session-1");
    state = sessionReducer(state, { type: "event", event: event(1, "assistant.delta", { content: "Hello " }) });
    state = sessionReducer(state, { type: "event", event: event(2, "assistant.delta", { content: "world" }) });
    expect(state.streamText).toBe("Hello world");
  });

  it("folds tool started and completed events into one card", () => {
    let state = initialSessionState("session-1");
    state = sessionReducer(state, { type: "event", event: event(1, "tool.started", { toolId: "tool-1", name: "read_file", inputSummary: "README.md" }) });
    state = sessionReducer(state, { type: "event", event: event(2, "tool.completed", { toolId: "tool-1", name: "read_file", isError: false, durationMs: 18, outputSummary: "done" }) });
    expect(state.toolOrder).toEqual(["tool-1"]);
    expect(state.tools["tool-1"]).toMatchObject({ status: "success", durationMs: 18, outputSummary: "done" });
    expect(state.timeline).toMatchObject([{ kind: "tool", toolId: "tool-1", turnId: "turn-1" }]);
  });

  it("keeps failed as a terminal status when an older snapshot arrives", () => {
    let state = initialSessionState("session-1");
    state = sessionReducer(state, { type: "event", event: event(5, "turn.failed", { message: "failed", errorType: "NameError", traceId: "trace-1" }) });
    const duplicate = event(4, "session.snapshot", { status: "idle", messages: [] });
    state = sessionReducer(state, { type: "event", event: duplicate });
    expect(state.status).toBe("failed");
  });

  it("drops duplicate events after reconnect", () => {
    let state = initialSessionState("session-1");
    const delta = event(3, "assistant.delta", { content: "once" });
    state = sessionReducer(state, { type: "event", event: delta });
    state = sessionReducer(state, { type: "event", event: delta });
    expect(state.streamText).toBe("once");
  });

  it("restores completed tool cards from a session snapshot", () => {
    const snapshot = event(7, "session.snapshot", {
      sessionId: "session-1",
      workspace: "/workspace",
      status: "completed",
      messages: [
        { role: "assistant_tool_call", toolUseId: "tool-1", toolName: "read_file", input: { path: "README.md" } },
        { role: "tool_result", toolUseId: "tool-1", toolName: "read_file", content: "contents", isError: false },
      ],
      pendingPermissions: [],
      error: null,
    });
    const state = sessionReducer(initialSessionState("session-1"), { type: "event", event: snapshot });

    expect(state.toolOrder).toEqual(["tool-1"]);
    expect(state.tools["tool-1"]).toMatchObject({ status: "success", outputSummary: "contents" });
    expect(state.timeline).toMatchObject([{ kind: "tool", toolId: "tool-1" }]);
  });

  it("restores pending permissions and failures into the snapshot timeline", () => {
    const snapshot = event(7, "session.snapshot", {
      sessionId: "session-1",
      workspace: "/workspace",
      status: "failed",
      messages: [{ role: "user", content: "Run it" }],
      activities: [{
        id: "activity-6",
        category: "progress",
        message: "Checking files",
        timestamp: "2026-06-19T00:00:00Z",
        turnId: "turn-1",
      }],
      pendingPermissions: [{
        requestId: "permission-1",
        kind: "shell",
        summary: "Run command",
        details: [],
        scope: "once",
        createdAt: 1,
      }],
      error: { message: "failed", errorType: "RuntimeError", traceId: "trace-1" },
    });

    const state = sessionReducer(initialSessionState("session-1"), { type: "event", event: snapshot });

    expect(state.timeline.map((item) => item.kind)).toEqual(["message", "permission", "error"]);
    expect(state.permissions["permission-1"]).toBeDefined();
    expect(state.activities).toMatchObject([{ message: "Checking files", turnId: "turn-1" }]);
    expect(state.timeline.at(-1)).toMatchObject({ kind: "error", traceId: "trace-1" });
  });

  it("keeps messages and tools in event order on the timeline", () => {
    let state = initialSessionState("session-1");
    state = sessionReducer(state, { type: "event", event: event(1, "turn.started", { message: "Question" }) });
    state = sessionReducer(state, { type: "event", event: event(2, "tool.started", { toolId: "tool-1", name: "read_file", inputSummary: "README.md" }) });
    state = sessionReducer(state, { type: "event", event: event(3, "assistant.completed", { content: "Answer" }) });

    expect(state.timeline.map((item) => item.kind)).toEqual(["message", "tool", "message"]);
    expect(state.timeline[0]).toMatchObject({ role: "user", content: "Question" });
    expect(state.timeline[1]).toMatchObject({ toolId: "tool-1" });
    expect(state.timeline[2]).toMatchObject({ role: "assistant", content: "Answer" });
  });

  it("turns a streaming assistant item into the final message", () => {
    let state = initialSessionState("session-1");
    state = sessionReducer(state, { type: "event", event: event(1, "assistant.delta", { content: "Hel" }) });
    state = sessionReducer(state, { type: "event", event: event(2, "assistant.delta", { content: "lo" }) });
    state = sessionReducer(state, { type: "event", event: event(3, "assistant.completed", { content: "Hello" }) });

    expect(state.streamText).toBe("");
    expect(state.timeline).toHaveLength(1);
    expect(state.timeline[0]).toMatchObject({ kind: "message", role: "assistant", content: "Hello", streaming: false });
  });
});
