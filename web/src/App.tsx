import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { api, connectSessionEvents } from "./api/client";
import type {
  DiffResponse,
  SessionSnapshot,
  SessionSummary,
  WebEvent,
} from "./api/types";
import { ChangesPanel } from "./features/changes/ChangesPanel";
import { ErrorCard } from "./features/chat/ErrorCard";
import { MarkdownMessage } from "./features/chat/MarkdownMessage";
import { MaxToolStepsCard } from "./features/chat/MaxToolStepsCard";
import { useTranscriptScroll } from "./features/chat/useTranscriptScroll";
import { PermissionCard } from "./features/permissions/PermissionCard";
import { ToolCard } from "./features/tools/ToolCard";
import { ToolGroup } from "./features/tools/ToolGroup";
import { groupTimelineTools, type PresentationalTimelineItem } from "./features/tools/toolGrouping";
import { initialSessionState, sessionReducer } from "./store/sessionStore";

const STATUS_LABELS = {
  idle: "Ready",
  running: "Working",
  waiting_permission: "Needs approval",
  failed: "Failed",
  incomplete: "Incomplete",
  completed: "Completed",
  cancelled: "Cancelled",
} as const;

// Bound exponential retries so an offline workspace becomes an explicit user action.
const MAX_RECONNECT_ATTEMPTS = 8;
const MAX_RECONNECT_DELAY_MS = 30_000;
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "summary",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

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

function reconnectDelay(attempt: number) {
  const base = Math.min(1_000 * 2 ** Math.max(0, attempt - 1), MAX_RECONNECT_DELAY_MS);
  const jitter = Math.round(base * (Math.random() * 0.25));
  return Math.min(base + jitter, MAX_RECONNECT_DELAY_MS);
}

function formatSyncTime(value: string) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function focusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
    .filter((element) => !element.hasAttribute("inert") && element.offsetParent !== null);
}

export function App() {
  const [state, dispatch] = useReducer(sessionReducer, undefined, () => initialSessionState());
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [isDiffLoading, setIsDiffLoading] = useState(false);
  const [rightTab, setRightTab] = useState<"changes" | "activity">("changes");
  const [mobilePanel, setMobilePanel] = useState<"sessions" | "context" | null>(null);
  const [isMobileLayout, setIsMobileLayout] = useState(false);
  const [notice, setNotice] = useState("");
  const [reconnectToken, setReconnectToken] = useState(0);
  const [dismissedErrors, setDismissedErrors] = useState<Record<string, boolean>>({});

  const maxSeqRef = useRef(0);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const sessionRailRef = useRef<HTMLElement>(null);
  const contextRailRef = useRef<HTMLElement>(null);
  const sessionTriggerRef = useRef<HTMLButtonElement>(null);
  const contextTriggerRef = useRef<HTMLButtonElement>(null);

  const isActive = state.status === "running" || state.status === "waiting_permission";
  const permissions = Object.values(state.permissions);
  const transcriptVersion = `${state.maxSeq}:${state.timeline.length}:${state.streamText.length}:${permissions.length}:${state.error?.traceId ?? ""}:${state.terminal?.reason ?? ""}`;
  const { isFollowing, unreadCount, followLatest } = useTranscriptScroll(transcriptRef, transcriptVersion);
  const presentationalTimeline = useMemo(
    () => groupTimelineTools(state.timeline, state.tools),
    [state.timeline, state.tools],
  );

  useEffect(() => {
    maxSeqRef.current = state.maxSeq;
  }, [state.maxSeq]);

  useEffect(() => {
    if (!isActive) setIsCancelling(false);
  }, [isActive]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 820px)");
    const update = () => setIsMobileLayout(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const closeMobilePanel = useCallback(() => {
    const panel = mobilePanel;
    setMobilePanel(null);
    requestAnimationFrame(() => {
      if (panel === "sessions") sessionTriggerRef.current?.focus();
      if (panel === "context") contextTriggerRef.current?.focus();
    });
  }, [mobilePanel]);

  useEffect(() => {
    const pairs: Array<[HTMLElement | null, boolean]> = [
      [sessionRailRef.current, mobilePanel === "sessions"],
      [contextRailRef.current, mobilePanel === "context"],
    ];
    for (const [node, isOpen] of pairs) {
      if (!node) continue;
      if (isMobileLayout && !isOpen) {
        node.setAttribute("inert", "");
        node.setAttribute("aria-hidden", "true");
      } else {
        node.removeAttribute("inert");
        node.removeAttribute("aria-hidden");
      }
    }
    document.body.classList.toggle("drawer-open", isMobileLayout && mobilePanel !== null);
  }, [isMobileLayout, mobilePanel]);

  useEffect(() => {
    if (!isMobileLayout || !mobilePanel) return undefined;
    const panel = mobilePanel === "sessions" ? sessionRailRef.current : contextRailRef.current;
    if (!panel) return undefined;

    requestAnimationFrame(() => {
      const [first] = focusableElements(panel);
      (first ?? panel).focus();
    });

    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        closeMobilePanel();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = focusableElements(panel);
      if (items.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [closeMobilePanel, isMobileLayout, mobilePanel]);

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
    if (!selectedSessionId) return undefined;
    let active = true;
    let socket: WebSocket | undefined;
    let retryTimer: number | undefined;
    let retryAttempt = 0;

    dispatch({ type: "reset", sessionId: selectedSessionId });
    maxSeqRef.current = 0;
    setDismissedErrors({});

    const scheduleReconnect = () => {
      if (!active) return;
      if (retryAttempt >= MAX_RECONNECT_ATTEMPTS) {
        dispatch({ type: "connection", status: "offline", retryAttempt, nextRetryAt: null });
        return;
      }
      retryAttempt += 1;
      const delay = reconnectDelay(retryAttempt);
      dispatch({
        type: "connection",
        status: "reconnecting",
        retryAttempt,
        nextRetryAt: Date.now() + delay,
      });
      retryTimer = window.setTimeout(connect, delay);
    };

    const connect = () => {
      if (!active) return;
      dispatch({
        type: "connection",
        status: maxSeqRef.current || retryAttempt ? "reconnecting" : "connecting",
        retryAttempt,
        nextRetryAt: null,
      });
      socket = connectSessionEvents(selectedSessionId, maxSeqRef.current, {
        onEvent: (event) => {
          maxSeqRef.current = Math.max(maxSeqRef.current, event.seq);
          dispatch({ type: "event", event });
          if (["turn.completed", "turn.failed", "turn.incomplete", "turn.cancelled"].includes(event.type)) {
            void api.listSessions().then((items) => {
              if (active) setSessions(items);
            });
          }
        },
        onOpen: () => {
          retryAttempt = 0;
          dispatch({ type: "connection", status: "connected", retryAttempt: 0, nextRetryAt: null });
        },
        onClose: scheduleReconnect,
      });
    };

    void api.getSession(selectedSessionId)
      .then((snapshot) => {
        if (!active) return;
        maxSeqRef.current = snapshot.lastSeq;
        dispatch({ type: "event", event: snapshotEvent(snapshot) });
        connect();
      })
      .catch((error) => {
        if (active) setNotice(error instanceof Error ? error.message : "Session could not be restored.");
      });

    return () => {
      active = false;
      socket?.close();
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, [selectedSessionId, reconnectToken]);

  useEffect(() => {
    if (!selectedSessionId) return undefined;
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
      setMobilePanel(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not create a session.");
    }
  }

  async function submitContent(content: string) {
    if (!content || !selectedSessionId || isSending || isActive) return;
    setIsSending(true);
    setNotice("");
    followLatest("auto");
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

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    await submitContent(draft.trim());
  }

  async function retryLastUserMessage() {
    const lastUser = [...state.messages].reverse().find((message) => message.role === "user");
    if (!lastUser) return;
    await submitContent(lastUser.content.trim());
  }

  async function cancelTurn() {
    if (!selectedSessionId || isCancelling) return;
    setIsCancelling(true);
    setNotice("");
    try {
      await api.cancelTurn(selectedSessionId);
    } catch (error) {
      setIsCancelling(false);
      setNotice(error instanceof Error ? error.message : "Could not cancel the turn.");
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function renderTimelineItem(item: PresentationalTimelineItem) {
    if (item.kind === "message") {
      return (
        <article className={`message message-${item.role} ${item.streaming ? "streaming" : ""}`}>
          <div className="message-label">{item.role === "user" ? "You" : item.streaming ? "MiniCode - writing" : "MiniCode"}</div>
          <div className="message-body">
            <MarkdownMessage content={item.content} idPrefix={item.id} />
            {item.streaming && <span className="cursor" />}
          </div>
        </article>
      );
    }
    if (item.kind === "tool") {
      const tool = state.tools[item.toolId];
      return tool ? <ToolCard tool={tool} /> : null;
    }
    if (item.kind === "tool-group") {
      const tools = item.toolIds.flatMap((toolId) => state.tools[toolId] ? [state.tools[toolId]] : []);
      return tools.length ? <ToolGroup tools={tools} /> : null;
    }
    if (item.kind === "permission") {
      const request = state.permissions[item.requestId];
      return request ? (
        <PermissionCard
          request={request}
          onResolve={(decision) => api.resolvePermission(request.requestId, decision).then(() => undefined)}
        />
      ) : null;
    }
    if (item.kind === "error") {
      const error = state.error;
      if (!error || error.traceId !== item.traceId || dismissedErrors[error.traceId]) return null;
      return (
        <ErrorCard
          error={error}
          onDismiss={() => setDismissedErrors((errors) => ({ ...errors, [error.traceId]: true }))}
          onRetry={() => void retryLastUserMessage()}
        />
      );
    }
    if (item.kind === "incomplete" && state.terminal) {
      return (
        <MaxToolStepsCard
          terminal={state.terminal}
          disabled={isSending || isActive}
          onContinue={() => void submitContent("Continue this task from the existing results. First summarize what is already known, then complete the remaining work without repeating finished tool calls.")}
        />
      );
    }
    return null;
  }

  const activeTitle = sessions.find((item) => item.sessionId === selectedSessionId)?.title || "New session";
  const lastSyncText = formatSyncTime(state.lastSyncedAt);

  return (
    <div className="app-shell">
      <div className="sr-status" role="status" aria-live="polite">
        {state.connection}. {STATUS_LABELS[state.status]}. {unreadCount ? `${unreadCount} new updates.` : ""}
      </div>
      {mobilePanel && (
        <button
          className="mobile-backdrop"
          aria-label="Close navigation panel"
          onClick={closeMobilePanel}
        />
      )}
      <aside
        ref={sessionRailRef}
        id="sessions-panel"
        className={`session-rail ${mobilePanel === "sessions" ? "mobile-open" : ""}`}
        aria-label="Sessions"
        tabIndex={-1}
      >
        <header className="brand-block">
          <div className="brand-mark">M</div>
          <div><strong>MiniCode</strong><small>Local workspace</small></div>
        </header>
        <button className="new-session" onClick={() => void createSession()}>+ New session</button>
        <nav className="session-list">
          {sessions.map((session) => (
            <button
              key={session.sessionId}
              className={session.sessionId === selectedSessionId ? "session-item selected" : "session-item"}
              onClick={() => {
                setSelectedSessionId(session.sessionId);
                closeMobilePanel();
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
          <button
            ref={sessionTriggerRef}
            className="mobile-nav-button"
            aria-label="Open sessions"
            aria-expanded={mobilePanel === "sessions"}
            aria-controls="sessions-panel"
            onClick={() => setMobilePanel("sessions")}
          >
            ☰
          </button>
          <div>
            <div className="eyebrow">Current session</div>
            <h1>{activeTitle}</h1>
          </div>
          <div className="header-statuses">
            <span className={`connection connection-${state.connection}`}>{state.connection}</span>
            {lastSyncText && <span className="sync-time">Synced {lastSyncText}</span>}
            <span className={`turn-status status-${state.status}`}>{STATUS_LABELS[state.status]}</span>
            {state.connection === "offline" && (
              <button className="quiet-button" onClick={() => setReconnectToken((token) => token + 1)}>Reconnect</button>
            )}
            {isActive && (
              <button className="quiet-button" disabled={isCancelling} onClick={() => void cancelTurn()}>
                {isCancelling ? "Cancelling..." : "Cancel"}
              </button>
            )}
            <button
              ref={contextTriggerRef}
              className="mobile-nav-button"
              aria-label="Open workspace context"
              aria-expanded={mobilePanel === "context"}
              aria-controls="context-panel"
              onClick={() => setMobilePanel("context")}
            >
              ◫
            </button>
          </div>
        </header>

        <section ref={transcriptRef} className="transcript" aria-label="Conversation timeline">
          {state.timeline.length === 0 && (
            <div className="welcome-card">
              <div className="welcome-icon">⌁</div>
              <h2>What should we work on?</h2>
              <p>Ask about this repository, request a change, or investigate a failure. Tools and approvals stay visible as the agent works.</p>
            </div>
          )}
          {presentationalTimeline.map((item) => (
            <div key={item.id} className={`timeline-item timeline-${item.kind}`}>
              {renderTimelineItem(item)}
            </div>
          ))}
        </section>

        <div className={`follow-latest-dock ${isFollowing ? "" : "visible"}`}>
          {!isFollowing && (
            <button type="button" className="follow-latest" onClick={() => followLatest()}>
              Back to latest{unreadCount > 0 ? ` · ${unreadCount}` : ""}
            </button>
          )}
        </div>

        <footer className="composer-wrap">
          {notice && <div className="notice" role="status">{notice}<button aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>}
          <form className="composer" onSubmit={(event) => void sendMessage(event)}>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder={state.status === "waiting_permission" ? "Resolve the approval request to continue" : "Ask MiniCode to inspect, explain, or change this workspace..."}
              aria-label="Message MiniCode"
              rows={2}
            />
            <button className="send-button" disabled={!draft.trim() || isSending || isActive} aria-label="Send message">↑</button>
          </form>
        </footer>
      </main>

      <aside
        ref={contextRailRef}
        id="context-panel"
        className={`context-rail ${mobilePanel === "context" ? "mobile-open" : ""}`}
        aria-label="Workspace context"
        tabIndex={-1}
      >
        <div className="context-tabs" role="tablist" aria-label="Workspace context">
          <button
            id="tab-changes"
            role="tab"
            aria-selected={rightTab === "changes"}
            aria-controls="panel-changes"
            onClick={() => setRightTab("changes")}
          >
            Changes {diff && diff.files.length > 0 && <span>{diff.files.length}</span>}
          </button>
          <button
            id="tab-activity"
            role="tab"
            aria-selected={rightTab === "activity"}
            aria-controls="panel-activity"
            onClick={() => setRightTab("activity")}
          >
            Activity
          </button>
        </div>
        <div className="context-content">
          {rightTab === "changes" ? (
            <div id="panel-changes" role="tabpanel" aria-labelledby="tab-changes">
              <ChangesPanel diff={diff} loading={isDiffLoading} sessionId={selectedSessionId} />
            </div>
          ) : (
            <div id="panel-activity" role="tabpanel" aria-labelledby="tab-activity">
              {state.activities.length ? (
                <ol className="activity-list">
                  {state.activities.map((activity) => (
                    <li key={activity.id}><span>{activity.category}</span><p>{activity.message || "Runtime state updated"}</p></li>
                  ))}
                </ol>
              ) : (
                <p className="empty-note">Runtime phases will appear here while the agent works.</p>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
