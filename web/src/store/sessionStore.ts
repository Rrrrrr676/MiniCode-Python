import type {
  ActivityItem,
  ConnectionStatus,
  ConversationMessage,
  FailurePayload,
  PermissionRequest,
  TimelineItem,
  TerminalPayload,
  ToolActivity,
  TurnStatus,
  WebEvent,
} from "../api/types";

export interface SessionViewState {
  sessionId: string;
  workspace: string;
  status: TurnStatus;
  connection: ConnectionStatus;
  retryAttempt: number;
  nextRetryAt: number | null;
  lastSyncedAt: string;
  maxSeq: number;
  messages: ConversationMessage[];
  streamText: string;
  tools: Record<string, ToolActivity>;
  toolOrder: string[];
  timeline: TimelineItem[];
  permissions: Record<string, PermissionRequest>;
  activities: ActivityItem[];
  error: FailurePayload | null;
  terminal: TerminalPayload | null;
  diffRevision: number;
}

export type SessionAction =
  | { type: "event"; event: WebEvent }
  | { type: "connection"; status: ConnectionStatus; retryAttempt?: number; nextRetryAt?: number | null }
  | { type: "reset"; sessionId: string };

export function initialSessionState(sessionId = ""): SessionViewState {
  return {
    sessionId,
    workspace: "",
    status: "idle",
    connection: "connecting",
    retryAttempt: 0,
    nextRetryAt: null,
    lastSyncedAt: "",
    maxSeq: 0,
    messages: [],
    streamText: "",
    tools: {},
    toolOrder: [],
    timeline: [],
    permissions: {},
    activities: [],
    error: null,
    terminal: null,
    diffRevision: 0,
  };
}

function text(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function number(payload: Record<string, unknown>, key: string): number {
  const value = payload[key];
  return typeof value === "number" ? value : 0;
}

function messagesFromSnapshot(raw: unknown): ConversationMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item, index) => {
    if (!item || typeof item !== "object") return [];
    const candidate = item as Record<string, unknown>;
    if ((candidate.role !== "user" && candidate.role !== "assistant") || typeof candidate.content !== "string") {
      return [];
    }
    return [{ id: `snapshot-${index}`, role: candidate.role, content: candidate.content }];
  });
}

function permissionMap(raw: unknown): Record<string, PermissionRequest> {
  if (!Array.isArray(raw)) return {};
  return Object.fromEntries(
    raw
      .filter((item): item is PermissionRequest => Boolean(item && typeof item.requestId === "string"))
      .map((item) => [item.requestId, item]),
  );
}

function activitiesFromSnapshot(raw: unknown, fallbackTimestamp: string): ActivityItem[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item, index) => {
    if (!item || typeof item !== "object") return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.message !== "string") return [];
    return [{
      id: typeof candidate.id === "string" ? candidate.id : `activity-snapshot-${index}`,
      category: typeof candidate.category === "string" ? candidate.category : "runtime",
      message: candidate.message,
      timestamp: typeof candidate.timestamp === "string" ? candidate.timestamp : fallbackTimestamp,
      turnId: typeof candidate.turnId === "string" ? candidate.turnId : undefined,
    }];
  });
}

function toolsFromSnapshot(raw: unknown): {
  tools: Record<string, ToolActivity>;
  toolOrder: string[];
  timeline: TimelineItem[];
  messages: ConversationMessage[];
} {
  if (!Array.isArray(raw)) return { tools: {}, toolOrder: [], timeline: [], messages: [] };
  const tools: Record<string, ToolActivity> = {};
  const toolOrder: string[] = [];
  const timeline: TimelineItem[] = [];
  const messages: ConversationMessage[] = [];
  raw.forEach((item, index) => {
    if (!item || typeof item !== "object") return;
    const message = item as Record<string, unknown>;
    const seq = index + 1;
    const turnId = typeof message.turnId === "string" ? message.turnId : "snapshot";
    if ((message.role === "user" || message.role === "assistant") && typeof message.content === "string") {
      const id = `snapshot-${index}`;
      const restoredMessage: ConversationMessage = {
        id,
        role: message.role,
        content: message.content,
        turnId,
        seq,
      };
      messages.push(restoredMessage);
      timeline.push({ id, kind: "message", role: message.role, content: message.content, seq, turnId });
      return;
    }
    const toolId = typeof message.toolUseId === "string" ? message.toolUseId : "";
    if (!toolId) return;
    if (message.role === "assistant_tool_call") {
      tools[toolId] = {
        toolId,
        name: typeof message.toolName === "string" ? message.toolName : "tool",
        status: "running",
        inputSummary: JSON.stringify(message.input ?? {}),
        outputSummary: "",
        durationMs: null,
        turnId,
        startedSeq: seq,
      };
      if (!toolOrder.includes(toolId)) toolOrder.push(toolId);
      if (!timeline.some((item) => item.kind === "tool" && item.toolId === toolId)) {
        timeline.push({ id: `tool-${toolId}`, kind: "tool", toolId, seq, turnId });
      }
    }
    if (message.role === "tool_result") {
      const previous = tools[toolId];
      tools[toolId] = {
        toolId,
        name: typeof message.toolName === "string" ? message.toolName : previous?.name ?? "tool",
        status: message.isError === true ? "failed" : "success",
        inputSummary: previous?.inputSummary ?? "",
        outputSummary: typeof message.content === "string" ? message.content : "",
        durationMs: null,
        turnId: previous?.turnId ?? turnId,
        startedSeq: previous?.startedSeq ?? seq,
      };
      if (!toolOrder.includes(toolId)) toolOrder.push(toolId);
      if (!timeline.some((item) => item.kind === "tool" && item.toolId === toolId)) {
        timeline.push({ id: `tool-${toolId}`, kind: "tool", toolId, seq, turnId });
      }
    }
  });
  return { tools, toolOrder, timeline, messages };
}

function upsertToolTimeline(
  timeline: TimelineItem[],
  toolId: string,
  event: WebEvent,
): TimelineItem[] {
  if (!toolId || timeline.some((item) => item.kind === "tool" && item.toolId === toolId)) return timeline;
  return [...timeline, { id: `tool-${toolId}`, kind: "tool", toolId, seq: event.seq, turnId: event.turnId }];
}

function withStreamingMessage(
  timeline: TimelineItem[],
  event: WebEvent,
  content: string,
  done = false,
): TimelineItem[] {
  const streamId = `assistant-stream-${event.turnId || event.sessionId}`;
  const existing = timeline.find((item) => item.kind === "message" && item.id === streamId);
  if (!existing) {
    return [
      ...timeline,
      {
        id: done ? `assistant-${event.seq}` : streamId,
        kind: "message",
        role: "assistant",
        content,
        seq: event.seq,
        turnId: event.turnId,
        streaming: !done,
      },
    ];
  }
  return timeline.map((item) => (
    item.kind === "message" && item.id === streamId
      ? { ...item, id: done ? `assistant-${event.seq}` : item.id, content, streaming: !done }
      : item
  ));
}

export function sessionReducer(state: SessionViewState, action: SessionAction): SessionViewState {
  if (action.type === "reset") return initialSessionState(action.sessionId);
  if (action.type === "connection") {
    return {
      ...state,
      connection: action.status,
      retryAttempt: action.retryAttempt ?? (action.status === "connected" ? 0 : state.retryAttempt),
      nextRetryAt: action.nextRetryAt ?? (action.status === "connected" ? null : state.nextRetryAt),
    };
  }

  const event = action.event;
  if (event.seq <= state.maxSeq) return state;
  const base = { ...state, maxSeq: event.seq, lastSyncedAt: event.timestamp };

  switch (event.type) {
    case "session.snapshot": {
      const snapshotStatus = text(event.payload, "status") as TurnStatus;
      const snapshotError = event.payload.error as FailurePayload | null | undefined;
      const restoredTools = toolsFromSnapshot(event.payload.messages);
      const restoredPermissions = permissionMap(event.payload.pendingPermissions);
      // Pending prompts and failures are not persisted as conversation messages, so
      // rebuild their timeline entries after replaying the stored message sequence.
      const restoredTimeline = [...restoredTools.timeline];
      const snapshotTailSeq = restoredTimeline.length;
      Object.values(restoredPermissions).forEach((request, index) => {
        restoredTimeline.push({
          id: `permission-${request.requestId}`,
          kind: "permission",
          requestId: request.requestId,
          seq: snapshotTailSeq + index + 1,
          turnId: request.turnId ?? event.turnId,
        });
      });
      if (snapshotError) {
        restoredTimeline.push({
          id: `error-snapshot-${restoredTimeline.length + 1}`,
          kind: "error",
          traceId: snapshotError.traceId,
          seq: restoredTimeline.length + 1,
          turnId: event.turnId,
        });
      }
      const snapshotTerminal = event.payload.terminal as TerminalPayload | null | undefined;
      if (snapshotTerminal?.reason === "max_tool_steps") {
        restoredTimeline.push({
          id: `incomplete-snapshot-${restoredTimeline.length + 1}`,
          kind: "incomplete",
          reason: "max_tool_steps",
          seq: restoredTimeline.length + 1,
          turnId: event.turnId,
        });
      }
      return {
        ...base,
        sessionId: text(event.payload, "sessionId") || event.sessionId,
        workspace: text(event.payload, "workspace"),
        status: snapshotStatus || "idle",
        messages: restoredTools.messages.length ? restoredTools.messages : messagesFromSnapshot(event.payload.messages),
        streamText: "",
        tools: restoredTools.tools,
        toolOrder: restoredTools.toolOrder,
        timeline: restoredTimeline,
        activities: activitiesFromSnapshot(event.payload.activities, event.timestamp),
        permissions: restoredPermissions,
        error: snapshotError ?? null,
        terminal: snapshotTerminal ?? null,
      };
    }
    case "turn.started": {
      const content = text(event.payload, "message");
      const last = base.messages.at(-1);
      const shouldAppend = content && !(last?.role === "user" && last.content === content);
      const userMessage: ConversationMessage = {
        id: `user-${event.seq}`,
        role: "user",
        content,
        turnId: event.turnId,
        seq: event.seq,
      };
      return {
        ...base,
        status: "running",
        error: null,
        terminal: null,
        streamText: "",
        messages: shouldAppend ? [...base.messages, userMessage] : base.messages,
        timeline: shouldAppend
          ? [
              ...base.timeline.filter((item) => item.kind !== "incomplete"),
              { ...userMessage, kind: "message", seq: event.seq, turnId: event.turnId },
            ]
          : base.timeline.filter((item) => item.kind !== "incomplete"),
      };
    }
    case "assistant.delta":
      return {
        ...base,
        streamText: base.streamText + text(event.payload, "content"),
        timeline: withStreamingMessage(
          base.timeline,
          event,
          base.streamText + text(event.payload, "content"),
        ),
      };
    case "assistant.completed": {
      const content = text(event.payload, "content") || base.streamText;
      const assistantMessage: ConversationMessage = {
        id: `assistant-${event.seq}`,
        role: "assistant",
        content,
        turnId: event.turnId,
        seq: event.seq,
      };
      return {
        ...base,
        streamText: "",
        messages: content
          ? [...base.messages, assistantMessage]
          : base.messages,
        timeline: content ? withStreamingMessage(base.timeline, event, content, true) : base.timeline,
      };
    }
    case "tool.started": {
      const toolId = text(event.payload, "toolId");
      const tool: ToolActivity = {
        toolId,
        name: text(event.payload, "name"),
        status: "running",
        inputSummary: text(event.payload, "inputSummary"),
        outputSummary: "",
        durationMs: null,
        turnId: event.turnId,
        startedSeq: event.seq,
      };
      return {
        ...base,
        tools: { ...base.tools, [toolId]: tool },
        toolOrder: base.toolOrder.includes(toolId) ? base.toolOrder : [...base.toolOrder, toolId],
        timeline: upsertToolTimeline(base.timeline, toolId, event),
      };
    }
    case "tool.completed": {
      const toolId = text(event.payload, "toolId");
      const previous = base.tools[toolId];
      return {
        ...base,
        tools: {
          ...base.tools,
          [toolId]: {
            toolId,
            name: text(event.payload, "name") || previous?.name || "tool",
            status: event.payload.isError === true ? "failed" : "success",
            inputSummary: previous?.inputSummary ?? "",
            outputSummary: text(event.payload, "outputSummary"),
            durationMs: number(event.payload, "durationMs"),
            turnId: previous?.turnId ?? event.turnId,
            startedSeq: previous?.startedSeq ?? event.seq,
          },
        },
        toolOrder: base.toolOrder.includes(toolId) ? base.toolOrder : [...base.toolOrder, toolId],
        timeline: upsertToolTimeline(base.timeline, toolId, event),
      };
    }
    case "runtime.phase": {
      const item: ActivityItem = {
        id: `activity-${event.seq}`,
        category: text(event.payload, "category") || "runtime",
        message: text(event.payload, "message"),
        timestamp: event.timestamp,
        turnId: event.turnId,
      };
      return { ...base, activities: [...base.activities, item].slice(-100) };
    }
    case "permission.requested": {
      const request = { ...(event.payload as unknown as PermissionRequest), turnId: event.turnId };
      return {
        ...base,
        status: "waiting_permission",
        permissions: { ...base.permissions, [request.requestId]: request },
        timeline: [
          ...base.timeline.filter((item) => item.kind !== "incomplete"),
          { id: `permission-${request.requestId}`, kind: "permission", requestId: request.requestId, seq: event.seq, turnId: event.turnId },
        ],
      };
    }
    case "permission.resolved": {
      const requestId = text(event.payload, "requestId");
      const permissions = { ...base.permissions };
      delete permissions[requestId];
      return { ...base, status: "running", permissions };
    }
    case "turn.failed":
      return {
        ...base,
        status: "failed",
        error: event.payload as unknown as FailurePayload,
        timeline: [
          ...base.timeline,
          {
            id: `error-${text(event.payload, "traceId") || event.seq}`,
            kind: "error",
            traceId: text(event.payload, "traceId"),
            seq: event.seq,
            turnId: event.turnId,
          },
        ],
      };
    case "turn.incomplete": {
      const terminal = event.payload as unknown as TerminalPayload;
      return {
        ...base,
        status: "incomplete",
        terminal,
        timeline: [
          ...base.timeline.filter((item) => item.kind !== "incomplete"),
          {
            id: `incomplete-${event.seq}`,
            kind: "incomplete",
            reason: "max_tool_steps",
            seq: event.seq,
            turnId: event.turnId,
          },
        ],
      };
    }
    case "turn.completed":
      return { ...base, status: "completed" };
    case "turn.cancelled":
      return { ...base, status: "cancelled" };
    case "diff.updated":
      return { ...base, diffRevision: base.diffRevision + 1 };
    default:
      return base;
  }
}
