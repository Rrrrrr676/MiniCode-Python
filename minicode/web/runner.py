"""Agent lifecycle adapter for the local Web product surface."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from minicode.session import (
    SessionData,
    create_new_session,
    list_sessions,
    load_session,
    save_session,
)
from minicode.web.broker import EventBroker
from minicode.web.schemas import SessionSnapshot, SessionSummary, TurnStatus
from minicode.web.security import sanitize_for_web


logger = logging.getLogger(__name__)


class SessionNotFoundError(LookupError):
    pass


class TurnConflictError(RuntimeError):
    pass


class PermissionResolutionError(RuntimeError):
    pass


class TurnCancelledError(RuntimeError):
    pass


@dataclass(slots=True)
class TurnCallbacks:
    on_stream_chunk: Callable[[str], None]
    on_assistant_message: Callable[[str], None]
    on_progress_message: Callable[[str], None]
    on_runtime_event: Callable[[Any], None]
    on_tool_start: Callable[[str, dict[str, Any]], None]
    on_tool_result: Callable[[str, str, bool], None]


@dataclass(slots=True)
class TurnExecutionContext:
    session: SessionData
    message: str
    turn_id: str
    callbacks: TurnCallbacks
    permission_prompt: Callable[[dict[str, Any]], dict[str, Any]]
    cancel_event: threading.Event


class TurnExecutor(Protocol):
    def __call__(self, context: TurnExecutionContext) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class PermissionRequestState:
    request_id: str
    session_id: str
    turn_id: str
    request: dict[str, Any]
    created_at: float
    resolved: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None
    resolution_reason: str = "user"


@dataclass(slots=True)
class WebSessionState:
    session: SessionData
    status: TurnStatus = "idle"
    active_turn_id: str = ""
    last_error: dict[str, Any] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    future: Future[None] | None = None


class WebSessionRunner:
    """Runs one Agent turn at a time and exposes it as browser-safe events."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        broker: EventBroker | None = None,
        executor: TurnExecutor | None = None,
        permission_timeout: float = 120.0,
    ) -> None:
        self.workspace = str(Path(workspace).resolve())
        self.broker = broker or EventBroker()
        self._executor = executor or self._execute_agent_turn
        self._permission_timeout = max(0.05, permission_timeout)
        self._states: dict[str, WebSessionState] = {}
        self._permission_requests: dict[str, PermissionRequestState] = {}
        self._active_session_id = ""
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="minicode-web-turn")

    def close(self) -> None:
        with self._lock:
            for state in self._states.values():
                state.cancel_event.set()
            for request in self._permission_requests.values():
                if not request.resolved.is_set():
                    request.response = {"decision": "deny_once"}
                    request.resolution_reason = "shutdown"
                    request.resolved.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _load_state(self, session_id: str) -> WebSessionState:
        with self._lock:
            existing = self._states.get(session_id)
            if existing is not None:
                return existing
        session = load_session(session_id)
        if session is None or Path(session.workspace).resolve() != Path(self.workspace):
            raise SessionNotFoundError(session_id)
        state = WebSessionState(
            session=session,
            status="completed" if any(msg.get("role") == "assistant" for msg in session.messages) else "idle",
        )
        with self._lock:
            return self._states.setdefault(session_id, state)

    def create_session(self, *, title: str = "") -> SessionSnapshot:
        session = create_new_session(self.workspace)
        if title.strip():
            session.history.append(title.strip()[:120])
        save_session(session, force_full=True)
        state = WebSessionState(session=session)
        with self._lock:
            self._states[session.session_id] = state
        event = self.broker.publish(
            session_id=session.session_id,
            turn_id="",
            event_type="session.snapshot",
            payload=self._snapshot_payload(state),
        )
        return self.snapshot(session.session_id, last_seq=event.seq)

    def list_session_summaries(self) -> list[SessionSummary]:
        summaries: list[SessionSummary] = []
        for metadata in list_sessions():
            if Path(metadata.workspace).resolve() != Path(self.workspace):
                continue
            with self._lock:
                state = self._states.get(metadata.session_id)
            status: TurnStatus = state.status if state else (
                "completed" if metadata.message_count else "idle"
            )
            title = metadata.first_message or metadata.last_message or "New session"
            summaries.append(
                SessionSummary(
                    sessionId=metadata.session_id,
                    createdAt=metadata.created_at,
                    updatedAt=metadata.updated_at,
                    title=title,
                    messageCount=metadata.message_count,
                    status=status,
                )
            )
        return summaries

    def snapshot(self, session_id: str, *, last_seq: int | None = None) -> SessionSnapshot:
        state = self._load_state(session_id)
        payload = self._snapshot_payload(state)
        return SessionSnapshot(
            **payload,
            lastSeq=self.broker.current_seq(session_id) if last_seq is None else last_seq,
        )

    def publish_snapshot(self, session_id: str) -> Any:
        state = self._load_state(session_id)
        return self.broker.publish(
            session_id=session_id,
            turn_id=state.active_turn_id,
            event_type="session.snapshot",
            payload=self._snapshot_payload(state),
        )

    def _snapshot_payload(self, state: WebSessionState) -> dict[str, Any]:
        with self._lock:
            pending = [
                self._permission_payload(request)
                for request in self._permission_requests.values()
                if request.session_id == state.session.session_id and not request.resolved.is_set()
            ]
            return {
                "sessionId": state.session.session_id,
                "workspace": self.workspace,
                "status": state.status,
                "activeTurnId": state.active_turn_id,
                "messages": sanitize_for_web(state.session.messages),
                "pendingPermissions": pending,
                "error": sanitize_for_web(state.last_error),
            }

    def submit_message(self, session_id: str, content: str) -> tuple[str, int]:
        message = content.strip()
        if not message:
            raise ValueError("Message cannot be empty.")
        state = self._load_state(session_id)
        with self._lock:
            active_state = self._states.get(self._active_session_id) if self._active_session_id else None
            if active_state and active_state.future and not active_state.future.done():
                raise TurnConflictError("Another Agent turn is already running in this workspace.")
            if state.future and not state.future.done():
                raise TurnConflictError("This session already has an active Agent turn.")

            turn_id = f"turn-{uuid.uuid4().hex[:12]}"
            state.status = "running"
            state.active_turn_id = turn_id
            state.last_error = None
            state.cancel_event = threading.Event()
            state.session.messages.append({"role": "user", "content": message})
            state.session.history.append(message)
            save_session(state.session)
            self._active_session_id = session_id

            started = self.broker.publish(
                session_id=session_id,
                turn_id=turn_id,
                event_type="turn.started",
                payload={"message": sanitize_for_web(message), "status": "running"},
            )
            state.future = self._pool.submit(self._run_turn, state, message, turn_id)
            return turn_id, started.seq

    def cancel_turn(self, session_id: str) -> bool:
        state = self._load_state(session_id)
        with self._lock:
            if state.status not in {"running", "waiting_permission"}:
                return False
            state.cancel_event.set()
            for request in self._permission_requests.values():
                if request.session_id == session_id and not request.resolved.is_set():
                    request.response = {"decision": "deny_once"}
                    request.resolution_reason = "cancelled"
                    request.resolved.set()
            return True

    def resolve_permission(
        self,
        request_id: str,
        *,
        decision: str,
        feedback: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            request = self._permission_requests.get(request_id)
            if request is None:
                raise PermissionResolutionError("Permission request does not exist.")
            if request.resolved.is_set():
                raise PermissionResolutionError("Permission request was already resolved.")
            request.response = {"decision": decision, "feedback": feedback}
            request.resolution_reason = "user"
            request.resolved.set()
            return self._permission_payload(request)

    def pending_permissions(self, session_id: str) -> list[dict[str, Any]]:
        self._load_state(session_id)
        with self._lock:
            return [
                self._permission_payload(item)
                for item in self._permission_requests.values()
                if item.session_id == session_id and not item.resolved.is_set()
            ]

    def _permission_payload(self, request: PermissionRequestState) -> dict[str, Any]:
        return {
            "requestId": request.request_id,
            "kind": request.request.get("kind", "unknown"),
            "summary": request.request.get("summary", "Approval required"),
            "details": request.request.get("details", []),
            "scope": request.request.get("scope", ""),
            "choices": request.request.get("choices", []),
            "createdAt": request.created_at,
        }

    def _make_permission_prompt(
        self,
        state: WebSessionState,
        turn_id: str,
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def prompt(raw_request: dict[str, Any]) -> dict[str, Any]:
            if state.cancel_event.is_set():
                raise TurnCancelledError("Turn cancelled while awaiting permission.")
            request = PermissionRequestState(
                request_id=f"perm-{uuid.uuid4().hex[:12]}",
                session_id=state.session.session_id,
                turn_id=turn_id,
                request=sanitize_for_web(raw_request),
                created_at=time.time(),
            )
            with self._lock:
                self._permission_requests[request.request_id] = request
                state.status = "waiting_permission"
            self.broker.publish(
                session_id=request.session_id,
                turn_id=turn_id,
                event_type="permission.requested",
                payload=self._permission_payload(request),
            )

            if not request.resolved.wait(self._permission_timeout):
                with self._lock:
                    if not request.resolved.is_set():
                        request.response = {"decision": "deny_once"}
                        request.resolution_reason = "timeout"
                        request.resolved.set()

            response = request.response or {"decision": "deny_once"}
            with self._lock:
                if state.status == "waiting_permission":
                    state.status = "running"
            self.broker.publish(
                session_id=request.session_id,
                turn_id=turn_id,
                event_type="permission.resolved",
                payload={
                    "requestId": request.request_id,
                    "decision": response["decision"],
                    "reason": request.resolution_reason,
                },
            )
            if state.cancel_event.is_set():
                raise TurnCancelledError("Turn cancelled while awaiting permission.")
            return response

        return prompt

    def _run_turn(self, state: WebSessionState, message: str, turn_id: str) -> None:
        session_id = state.session.session_id
        tool_starts: dict[str, deque[tuple[str, float]]] = defaultdict(deque)
        callback_lock = threading.RLock()

        def check_cancelled() -> None:
            if state.cancel_event.is_set():
                raise TurnCancelledError("Turn cancelled by the user.")

        def publish(event_type: Any, payload: dict[str, Any]) -> None:
            check_cancelled()
            self.broker.publish(
                session_id=session_id,
                turn_id=turn_id,
                event_type=event_type,
                payload=sanitize_for_web(payload),
            )

        def on_tool_start(name: str, arguments: dict[str, Any]) -> None:
            tool_id = f"tool-{uuid.uuid4().hex[:12]}"
            with callback_lock:
                tool_starts[name].append((tool_id, time.monotonic()))
            serialized = json.dumps(sanitize_for_web(arguments), ensure_ascii=False, default=str)
            publish(
                "tool.started",
                {"toolId": tool_id, "name": name, "inputSummary": serialized[:600]},
            )

        def on_tool_result(name: str, output: str, is_error: bool) -> None:
            with callback_lock:
                tool_id, started_at = (
                    tool_starts[name].popleft()
                    if tool_starts[name]
                    else (f"tool-{uuid.uuid4().hex[:12]}", time.monotonic())
                )
            publish(
                "tool.completed",
                {
                    "toolId": tool_id,
                    "name": name,
                    "isError": is_error,
                    "durationMs": round((time.monotonic() - started_at) * 1000, 1),
                    "outputSummary": output[:2_000],
                },
            )
            publish("diff.updated", {"source": name})

        callbacks = TurnCallbacks(
            on_stream_chunk=lambda chunk: publish("assistant.delta", {"content": chunk}),
            on_assistant_message=lambda content: publish(
                "assistant.completed", {"content": content}
            ),
            on_progress_message=lambda message_text: publish(
                "runtime.phase", {"category": "progress", "message": message_text}
            ),
            on_runtime_event=lambda event: publish(
                "runtime.phase",
                asdict(event) if hasattr(event, "__dataclass_fields__") else {"message": str(event)},
            ),
            on_tool_start=on_tool_start,
            on_tool_result=on_tool_result,
        )
        context = TurnExecutionContext(
            session=state.session,
            message=message,
            turn_id=turn_id,
            callbacks=callbacks,
            permission_prompt=self._make_permission_prompt(state, turn_id),
            cancel_event=state.cancel_event,
        )

        try:
            result_messages = self._executor(context)
            check_cancelled()
            with self._lock:
                state.session.messages = [
                    sanitize_for_web(item)
                    for item in result_messages
                    if item.get("role") != "system"
                ]
                state.status = "completed"
                save_session(state.session, force_full=True)
            self.broker.publish(
                session_id=session_id,
                turn_id=turn_id,
                event_type="turn.completed",
                payload={"status": "completed"},
            )
        except TurnCancelledError:
            with self._lock:
                state.status = "cancelled"
                save_session(state.session, force_full=True)
            self.broker.publish(
                session_id=session_id,
                turn_id=turn_id,
                event_type="turn.cancelled",
                payload={"status": "cancelled"},
            )
        except Exception as exc:  # noqa: BLE001 - worker boundary converts to stable failure
            trace_id = f"trace-{uuid.uuid4().hex[:12]}"
            error = {
                "message": "The Agent turn failed. Check the local logs with this trace ID.",
                "errorType": type(exc).__name__,
                "traceId": trace_id,
            }
            logger.exception("Web Agent turn failed [%s]", trace_id)
            with self._lock:
                state.status = "failed"
                state.last_error = error
                save_session(state.session, force_full=True)
            self.broker.publish(
                session_id=session_id,
                turn_id=turn_id,
                event_type="turn.failed",
                payload=error,
            )
        finally:
            with self._lock:
                if self._active_session_id == session_id:
                    self._active_session_id = ""
                state.active_turn_id = ""

    def _execute_agent_turn(self, context: TurnExecutionContext) -> list[dict[str, Any]]:
        """Lazy core-runtime integration keeps Web dependencies optional."""
        from minicode.agent_loop import run_agent_turn
        from minicode.config import load_runtime_config
        from minicode.memory import MemoryManager
        from minicode.model_registry import create_model_adapter
        from minicode.permissions import PermissionManager
        from minicode.prompt import build_system_prompt
        from minicode.tools import create_default_tool_registry

        runtime = load_runtime_config(self.workspace)
        tools = create_default_tool_registry(self.workspace, runtime=runtime)
        permissions = PermissionManager(self.workspace, prompt=context.permission_prompt)
        memory = MemoryManager(project_root=Path(self.workspace))
        model = create_model_adapter(
            model=runtime.get("model", ""),
            tools=tools,
            runtime=runtime,
        )
        system_prompt = build_system_prompt(
            self.workspace,
            permissions.get_summary(),
            {
                "skills": tools.get_skills(),
                "mcpServers": tools.get_mcp_servers(),
                "memory_context": memory.get_relevant_context(query=context.message),
                "runtime": runtime,
            },
        )
        messages = [{"role": "system", "content": system_prompt}, *context.session.messages]
        permissions.begin_turn()
        try:
            return run_agent_turn(
                model=model,
                tools=tools,
                messages=messages,
                cwd=self.workspace,
                permissions=permissions,
                session=context.session,
                runtime=runtime,
                on_tool_start=context.callbacks.on_tool_start,
                on_tool_result=context.callbacks.on_tool_result,
                on_assistant_message=context.callbacks.on_assistant_message,
                on_progress_message=context.callbacks.on_progress_message,
                on_runtime_event=context.callbacks.on_runtime_event,
                on_assistant_stream_chunk=context.callbacks.on_stream_chunk,
            )
        finally:
            permissions.end_turn()
            try:
                tools.dispose()
            except Exception:  # noqa: BLE001 - cleanup must not rewrite turn outcome
                logger.warning("Failed to dispose Web turn tools", exc_info=True)
