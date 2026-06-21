export type TurnStatus =
  | "idle"
  | "running"
  | "waiting_permission"
  | "failed"
  | "completed"
  | "cancelled";

export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "offline";

export interface SessionSummary {
  sessionId: string;
  createdAt: number;
  updatedAt: number;
  title: string;
  messageCount: number;
  status: TurnStatus;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export interface PermissionRequest {
  requestId: string;
  kind: string;
  summary: string;
  details: string[];
  scope: string;
  createdAt: number;
}

export interface SessionSnapshot {
  sessionId: string;
  workspace: string;
  status: TurnStatus;
  activeTurnId: string;
  lastSeq: number;
  messages: Array<Record<string, unknown>>;
  pendingPermissions: PermissionRequest[];
  error: FailurePayload | null;
}

export interface FailurePayload {
  message: string;
  errorType: string;
  traceId: string;
}

export interface ToolActivity {
  toolId: string;
  name: string;
  status: "running" | "success" | "failed";
  inputSummary: string;
  outputSummary: string;
  durationMs: number | null;
}

export interface ActivityItem {
  id: string;
  category: string;
  message: string;
  timestamp: string;
}

export interface DiffFile {
  path: string;
  additions: number;
  deletions: number;
  patch: string;
}

export interface DiffResponse {
  files: DiffFile[];
  additions: number;
  deletions: number;
  truncated: boolean;
}

export type WebEventType =
  | "session.snapshot"
  | "turn.started"
  | "runtime.phase"
  | "assistant.delta"
  | "assistant.completed"
  | "tool.started"
  | "tool.completed"
  | "permission.requested"
  | "permission.resolved"
  | "diff.updated"
  | "turn.failed"
  | "turn.completed"
  | "turn.cancelled";

export interface WebEvent {
  seq: number;
  sessionId: string;
  turnId: string;
  type: WebEventType;
  timestamp: string;
  payload: Record<string, unknown>;
}
