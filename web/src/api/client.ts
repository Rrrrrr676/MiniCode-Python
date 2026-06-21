import type {
  DiffResponse,
  SessionSnapshot,
  SessionSummary,
  WebEvent,
} from "./types";

interface ApiErrorBody {
  error?: { message?: string; code?: string };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new Error(body.error?.message ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export const api = {
  listSessions: () => request<SessionSummary[]>("/api/sessions"),
  createSession: () =>
    request<SessionSnapshot>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "" }),
    }),
  getSession: (sessionId: string) =>
    request<SessionSnapshot>(`/api/sessions/${encodeURIComponent(sessionId)}`),
  sendMessage: (sessionId: string, content: string) =>
    request<{ turnId: string; accepted: boolean; seq: number }>(
      `/api/sessions/${encodeURIComponent(sessionId)}/messages`,
      { method: "POST", body: JSON.stringify({ content }) },
    ),
  cancelTurn: (sessionId: string) =>
    request<{ accepted: boolean }>(`/api/sessions/${encodeURIComponent(sessionId)}/cancel`, {
      method: "POST",
    }),
  resolvePermission: (requestId: string, decision: string) =>
    request<{ resolved: boolean }>(`/api/permissions/${encodeURIComponent(requestId)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ decision, feedback: "" }),
    }),
  getDiff: (sessionId: string) =>
    request<DiffResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/diff`),
};

export function connectSessionEvents(
  sessionId: string,
  after: number,
  handlers: {
    onEvent: (event: WebEvent) => void;
    onOpen: () => void;
    onClose: () => void;
  },
): WebSocket {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${scheme}://${window.location.host}/api/sessions/${encodeURIComponent(sessionId)}/events?after=${after}`;
  const socket = new WebSocket(url);
  socket.onopen = handlers.onOpen;
  socket.onmessage = (message) => handlers.onEvent(JSON.parse(message.data) as WebEvent);
  socket.onclose = handlers.onClose;
  socket.onerror = () => socket.close();
  return socket;
}
