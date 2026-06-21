export type TurnStatus =
  | "idle"
  | "running"
  | "waiting_permission"
  | "failed"
  | "incomplete"
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
  turnId?: string;
  seq?: number;
}

export interface PermissionRequest {
  requestId: string;
  kind: string;
  summary: string;
  details: string[];
  scope: string;
  choices?: PermissionDecision[];
  createdAt: number;
  turnId?: string;
}

export type PermissionDecision =
  | "allow_once"
  | "allow_always"
  | "allow_turn"
  | "allow_all_turn"
  | "deny_once"
  | "deny_always"
  | "deny_with_feedback";

export interface SessionSnapshot {
  sessionId: string;
  workspace: string;
  status: TurnStatus;
  activeTurnId: string;
  lastSeq: number;
  messages: Array<Record<string, unknown>>;
  activities: ActivityItem[];
  pendingPermissions: PermissionRequest[];
  error: FailurePayload | null;
  terminal?: TerminalPayload | null;
}

export interface TerminalPayload {
  reason: "max_tool_steps";
  usedSteps: number;
  maxSteps: number;
  message: string;
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
  turnId?: string;
  startedSeq?: number;
}

export interface ActivityItem {
  id: string;
  category: string;
  message: string;
  timestamp: string;
  turnId?: string;
}

export type TimelineItem =
  | {
      id: string;
      kind: "message";
      role: "user" | "assistant";
      content: string;
      seq: number;
      turnId: string;
      streaming?: boolean;
    }
  | { id: string; kind: "tool"; toolId: string; seq: number; turnId: string }
  | { id: string; kind: "permission"; requestId: string; seq: number; turnId: string }
  | { id: string; kind: "error"; traceId: string; seq: number; turnId: string }
  | { id: string; kind: "incomplete"; reason: "max_tool_steps"; seq: number; turnId: string };

export interface ConnectionState {
  status: ConnectionStatus;
  retryAttempt?: number;
  nextRetryAt?: number;
  lastSyncedAt?: string;
}

export interface DiffFile {
  path: string;
  additions: number;
  deletions: number;
  status: "added" | "copied" | "deleted" | "modified" | "renamed" | "untracked" | string;
  isBinary: boolean;
}

export interface DiffResponse {
  files: DiffFile[];
  additions: number;
  deletions: number;
  truncated: boolean;
  revision: string;
}

export interface DiffPatchResponse extends DiffFile {
  patch: string;
  truncated: boolean;
  revision: string;
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
  | "turn.incomplete"
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
