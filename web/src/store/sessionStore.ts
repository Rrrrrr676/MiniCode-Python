import type {
  ActivityItem,
  ConnectionStatus,
  ConversationMessage,
  FailurePayload,
  PermissionRequest,
  ToolActivity,
  TurnStatus,
  WebEvent,
} from "../api/types";

export interface SessionViewState {
  sessionId: string;
  workspace: string;
  status: TurnStatus;
  connection: ConnectionStatus;
  maxSeq: number;
  messages: ConversationMessage[];
  streamText: string;
  tools: Record<string, ToolActivity>;
  toolOrder: string[];
  permissions: Record<string, PermissionRequest>;
  activities: ActivityItem[];
  error: FailurePayload | null;
  diffRevision: number;
}

export type SessionAction =
  | { type: "event"; event: WebEvent }
  | { type: "connection"; status: ConnectionStatus }
  | { type: "reset"; sessionId: string };

export function initialSessionState(sessionId = ""): SessionViewState {
  return {
    sessionId,
    workspace: "",
    status: "idle",
    connection: "connecting",
    maxSeq: 0,
    messages: [],
    streamText: "",
    tools: {},
    toolOrder: [],
    permissions: {},
    activities: [],
    error: null,
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

function toolsFromSnapshot(raw: unknown): {
  tools: Record<string, ToolActivity>;
  toolOrder: string[];
} {
  if (!Array.isArray(raw)) return { tools: {}, toolOrder: [] };
  const tools: Record<string, ToolActivity> = {};
  const toolOrder: string[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const message = item as Record<string, unknown>;
    const toolId = typeof message.toolUseId === "string" ? message.toolUseId : "";
    if (!toolId) continue;
    if (message.role === "assistant_tool_call") {
      tools[toolId] = {
        toolId,
        name: typeof message.toolName === "string" ? message.toolName : "tool",
        status: "running",
        inputSummary: JSON.stringify(message.input ?? {}),
        outputSummary: "",
        durationMs: null,
      };
      if (!toolOrder.includes(toolId)) toolOrder.push(toolId);
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
      };
      if (!toolOrder.includes(toolId)) toolOrder.push(toolId);
    }
  }
  return { tools, toolOrder };
}

export function sessionReducer(state: SessionViewState, action: SessionAction): SessionViewState {
  if (action.type === "reset") return initialSessionState(action.sessionId);
  if (action.type === "connection") return { ...state, connection: action.status };

  const event = action.event;
  if (event.seq <= state.maxSeq) return state;
  const base = { ...state, maxSeq: event.seq };

  switch (event.type) {
    case "session.snapshot": {
      const snapshotStatus = text(event.payload, "status") as TurnStatus;
      const snapshotError = event.payload.error as FailurePayload | null | undefined;
      const restoredTools = toolsFromSnapshot(event.payload.messages);
      return {
        ...base,
        sessionId: text(event.payload, "sessionId") || event.sessionId,
        workspace: text(event.payload, "workspace"),
        status: snapshotStatus || "idle",
        messages: messagesFromSnapshot(event.payload.messages),
        streamText: "",
        tools: restoredTools.tools,
        toolOrder: restoredTools.toolOrder,
        permissions: permissionMap(event.payload.pendingPermissions),
        error: snapshotError ?? null,
      };
    }
    case "turn.started": {
      const content = text(event.payload, "message");
      const last = base.messages.at(-1);
      return {
        ...base,
        status: "running",
        error: null,
        streamText: "",
        messages:
          content && !(last?.role === "user" && last.content === content)
            ? [...base.messages, { id: `user-${event.seq}`, role: "user", content }]
            : base.messages,
      };
    }
    case "assistant.delta":
      return { ...base, streamText: base.streamText + text(event.payload, "content") };
    case "assistant.completed": {
      const content = text(event.payload, "content") || base.streamText;
      return {
        ...base,
        streamText: "",
        messages: content
          ? [...base.messages, { id: `assistant-${event.seq}`, role: "assistant", content }]
          : base.messages,
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
      };
      return {
        ...base,
        tools: { ...base.tools, [toolId]: tool },
        toolOrder: base.toolOrder.includes(toolId) ? base.toolOrder : [...base.toolOrder, toolId],
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
          },
        },
        toolOrder: base.toolOrder.includes(toolId) ? base.toolOrder : [...base.toolOrder, toolId],
      };
    }
    case "runtime.phase": {
      const item: ActivityItem = {
        id: `activity-${event.seq}`,
        category: text(event.payload, "category") || "runtime",
        message: text(event.payload, "message"),
        timestamp: event.timestamp,
      };
      return { ...base, activities: [...base.activities, item].slice(-100) };
    }
    case "permission.requested": {
      const request = event.payload as unknown as PermissionRequest;
      return {
        ...base,
        status: "waiting_permission",
        permissions: { ...base.permissions, [request.requestId]: request },
      };
    }
    case "permission.resolved": {
      const requestId = text(event.payload, "requestId");
      const permissions = { ...base.permissions };
      delete permissions[requestId];
      return { ...base, status: "running", permissions };
    }
    case "turn.failed":
      return { ...base, status: "failed", error: event.payload as unknown as FailurePayload };
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
