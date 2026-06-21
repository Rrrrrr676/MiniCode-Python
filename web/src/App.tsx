import { FormEvent, useEffect, useReducer, useRef, useState } from "react";
import { api, connectSessionEvents } from "./api/client";
import type { DiffResponse, SessionSnapshot, SessionSummary, WebEvent } from "./api/types";
import { ChangesPanel } from "./features/changes/ChangesPanel";
import { ErrorCard } from "./features/chat/ErrorCard";
import { PermissionCard } from "./features/permissions/PermissionCard";
import { ToolCard } from "./features/tools/ToolCard";
import { initialSessionState, sessionReducer } from "./store/sessionStore";

const STATUS_LABELS = {
  idle: "Ready",
  running: "Working",
  waiting_permission: "Needs approval",
  failed: "Failed",
  completed: "Completed",
  cancelled: "Cancelled",
} as const;

function snapshotEvent(snapshot: SessionSnapshot): WebEvent {
  return {
    seq: snapshot.lastSeq,
    sessionId: snapshot.sessionId,
    turnId: snapshot.activeTurnId,
    type: "session.snapshot",
    timestamp: new Date().toISOString(),
    payload: snapshot as unknown as Record<string, unknown>,
  };
}

export function App() {
  const [state, dispatch] = useReducer(sessionReducer, undefined, () => initialSessionState());
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [isDiffLoading, setIsDiffLoading] = useState(false);
  const [rightTab, setRightTab] = useState<"changes" | "activity">("changes");
  const [mobilePanel, setMobilePanel] = useState<"sessions" | "context" | null>(null);
  const [notice, setNotice] = useState("");
  const maxSeqRef = useRef(0);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    maxSeqRef.current = state.maxSeq;
  }, [state.maxSeq]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        let items = await api.listSessions();
        if (items.length === 0) {
          const created = await api.createSession();
          items = await api.listSessions();
          if (active) setSelectedSessionId(created.sessionId);
        } else if (active) {
          setSelectedSessionId(items[0].sessionId);
        }
        if (active) setSessions(items);
      } catch (error) {
        if (active) setNotice(error instanceof Error ? error.message : "Could not open the workspace.");
      }
    })();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selectedSessionId) return;
    let active = true;
    let socket: WebSocket | undefined;
    let retryTimer: number | undefined;

    dispatch({ type: "reset", sessionId: selectedSessionId });
    maxSeqRef.current = 0;

    const connect = () => {
      if (!active) return;
      dispatch({ type: "connection", status: maxSeqRef.current ? "reconnecting" : "connecting" });
      socket = connectSessionEvents(selectedSessionId, maxSeqRef.current, {
        onEvent: (event) => {
          maxSeqRef.current = Math.max(maxSeqRef.current, event.seq);
          dispatch({ type: "event", event });
          if (["turn.completed", "turn.failed", "turn.cancelled"].includes(event.type)) {
            void api.listSessions().then((items) => {
              if (active) setSessions(items);
            });
          }
        },
        onOpen: () => dispatch({ type: "connection", status: "connected" }),
        onClose: () => {
          if (!active) return;
          dispatch({ type: "connection", status: "reconnecting" });
          retryTimer = window.setTimeout(connect, 1_000);
        },
      });
    };

    void api.getSession(selectedSessionId)
      .then((snapshot) => {
        if (!active) return;
        maxSeqRef.current = snapshot.lastSeq;
        dispatch({ type: "event", event: snapshotEvent(snapshot) });
        connect();
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "Session could not be restored."));

    return () => {
      active = false;
      socket?.close();
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, [selectedSessionId]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.messages, state.streamText, state.permissions]);

  useEffect(() => {
    if (!selectedSessionId) return;
    let active = true;
    setIsDiffLoading(true);
    void api.getDiff(selectedSessionId)
      .then((nextDiff) => { if (active) setDiff(nextDiff); })
      .catch((error) => { if (active) setNotice(error instanceof Error ? error.message : "Could not read changes."); })
      .finally(() => { if (active) setIsDiffLoading(false); });
    return () => { active = false; };
  }, [selectedSessionId, state.diffRevision]);

  async function refreshSessions() {
    setSessions(await api.listSessions());
  }

  async function createSession() {
    try {
      const created = await api.createSession();
      await refreshSessions();
      setSelectedSessionId(created.sessionId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not create a session.");
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || !selectedSessionId || isSending) return;
    setIsSending(true);
    setNotice("");
    try {
      await api.sendMessage(selectedSessionId, content);
      setDraft("");
      await refreshSessions();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Message could not be sent.");
    } finally {
      setIsSending(false);
    }
  }

  const isActive = state.status === "running" || state.status === "waiting_permission";
  const tools = state.toolOrder.map((id) => state.tools[id]).filter(Boolean);
  const permissions = Object.values(state.permissions);

  return (
    <div className="app-shell">
      {mobilePanel && (
        <button
          className="mobile-backdrop"
          aria-label="Close navigation panel"
          onClick={() => setMobilePanel(null)}
        />
      )}
      <aside className={`session-rail ${mobilePanel === "sessions" ? "mobile-open" : ""}`} aria-label="Sessions">
        <header className="brand-block">
          <div className="brand-mark">M</div>
          <div><strong>MiniCode</strong><small>Local workspace</small></div>
        </header>
        <button className="new-session" onClick={() => void createSession()}>＋ New session</button>
        <nav className="session-list">
          {sessions.map((session) => (
            <button
              key={session.sessionId}
              className={session.sessionId === selectedSessionId ? "session-item selected" : "session-item"}
              onClick={() => {
                setSelectedSessionId(session.sessionId);
                setMobilePanel(null);
              }}
            >
              <span>{session.title}</span>
              <small>{session.messageCount} messages · {STATUS_LABELS[session.status]}</small>
            </button>
          ))}
        </nav>
        <footer className="workspace-card">
          <span className="status-dot" />
          <div><strong>{state.workspace.split("/").at(-1) || "Workspace"}</strong><small>127.0.0.1 · private</small></div>
        </footer>
      </aside>

      <main className="conversation">
        <header className="conversation-header">
          <button className="mobile-nav-button" aria-label="Open sessions" onClick={() => setMobilePanel("sessions")}>☰</button>
          <div>
            <div className="eyebrow">Current session</div>
            <h1>{sessions.find((item) => item.sessionId === selectedSessionId)?.title || "New session"}</h1>
          </div>
          <div className="header-statuses">
            <span className={`connection connection-${state.connection}`}>{state.connection}</span>
            <span className={`turn-status status-${state.status}`}>{STATUS_LABELS[state.status]}</span>
            {isActive && <button className="quiet-button" onClick={() => void api.cancelTurn(selectedSessionId)}>Cancel</button>}
            <button className="mobile-nav-button" aria-label="Open workspace context" onClick={() => setMobilePanel("context")}>◫</button>
          </div>
        </header>

        <section className="transcript" aria-live="polite">
          {state.messages.length === 0 && !state.streamText && (
            <div className="welcome-card">
              <div className="welcome-icon">⌁</div>
              <h2>What should we work on?</h2>
              <p>Ask about this repository, request a change, or investigate a failure. Tools and approvals stay visible as the agent works.</p>
            </div>
          )}
          {state.messages.map((message) => (
            <article key={message.id} className={`message message-${message.role}`}>
              <div className="message-label">{message.role === "user" ? "You" : "MiniCode"}</div>
              <div className="message-body">{message.content}</div>
            </article>
          ))}
          {state.streamText && (
            <article className="message message-assistant streaming">
              <div className="message-label">MiniCode · writing</div>
              <div className="message-body">{state.streamText}<span className="cursor" /></div>
            </article>
          )}
          {tools.length > 0 && (
            <section className="tool-stack" aria-label="Tool activity">
              <div className="section-label">Tool activity</div>
              {tools.map((tool) => <ToolCard key={tool.toolId} tool={tool} />)}
            </section>
          )}
          {permissions.map((request) => (
            <PermissionCard
              key={request.requestId}
              request={request}
              onResolve={(decision) => api.resolvePermission(request.requestId, decision).then(() => undefined)}
            />
          ))}
          {state.error && <ErrorCard error={state.error} />}
          <div ref={transcriptEndRef} />
        </section>

        <footer className="composer-wrap">
          {notice && <div className="notice" role="status">{notice}<button aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>}
          <form className="composer" onSubmit={(event) => void sendMessage(event)}>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={state.status === "waiting_permission" ? "Resolve the approval request to continue" : "Ask MiniCode to inspect, explain, or change this workspace…"}
              aria-label="Message MiniCode"
              disabled={isActive}
              rows={2}
            />
            <button className="send-button" disabled={!draft.trim() || isSending || isActive} aria-label="Send message">↑</button>
          </form>
          <small>Enter to send · Shift + Enter for a new line</small>
        </footer>
      </main>

      <aside className={`context-rail ${mobilePanel === "context" ? "mobile-open" : ""}`} aria-label="Workspace context">
        <div className="context-tabs" role="tablist">
          <button role="tab" aria-selected={rightTab === "changes"} onClick={() => setRightTab("changes")}>
            Changes {diff && diff.files.length > 0 && <span>{diff.files.length}</span>}
          </button>
          <button role="tab" aria-selected={rightTab === "activity"} onClick={() => setRightTab("activity")}>Activity</button>
        </div>
        <div className="context-content">
          {rightTab === "changes" ? (
            <ChangesPanel diff={diff} loading={isDiffLoading} />
          ) : state.activities.length ? (
            <ol className="activity-list">
              {state.activities.map((activity) => (
                <li key={activity.id}><span>{activity.category}</span><p>{activity.message || "Runtime state updated"}</p></li>
              ))}
            </ol>
          ) : (
            <p className="empty-note">Runtime phases will appear here while the agent works.</p>
          )}
        </div>
      </aside>
    </div>
  );
}
