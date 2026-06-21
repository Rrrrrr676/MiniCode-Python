"""REST and WebSocket routes for the local Web console."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from minicode.web import __version__
from minicode.web.diff import MAX_EXPANDED_DIFF_BYTES, read_workspace_diff, read_workspace_diff_file
from minicode.web.runner import (
    PermissionResolutionError,
    SessionNotFoundError,
    TurnConflictError,
    WebSessionRunner,
)
from minicode.web.schemas import (
    CreateSessionRequest,
    DiffPatchResponse,
    DiffResponse,
    MessageRequest,
    PermissionResolveRequest,
    SessionSnapshot,
    SessionSummary,
)


def _error(code: str, message: str, *, http_status: int, retryable: bool = False) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={
            "code": code,
            "message": message,
            "traceId": f"trace-{uuid.uuid4().hex[:12]}",
            "retryable": retryable,
        },
    )


def create_api_router(runner: WebSessionRunner) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/status")
    def get_status() -> dict[str, object]:
        return {
            "version": __version__,
            "ready": True,
            "host": "127.0.0.1",
            "workspace": Path(runner.workspace).name,
            "singleActiveTurn": True,
        }

    @router.get("/sessions", response_model=list[SessionSummary])
    def get_sessions() -> list[SessionSummary]:
        return runner.list_session_summaries()

    @router.post("/sessions", response_model=SessionSnapshot, status_code=status.HTTP_201_CREATED)
    def create_session(request: CreateSessionRequest) -> SessionSnapshot:
        return runner.create_session(title=request.title)

    @router.get("/sessions/{session_id}", response_model=SessionSnapshot)
    def get_session(session_id: str) -> SessionSnapshot:
        try:
            return runner.snapshot(session_id)
        except SessionNotFoundError as exc:
            raise _error(
                "SESSION_NOT_FOUND",
                "Session does not exist in the current workspace.",
                http_status=status.HTTP_404_NOT_FOUND,
            ) from exc

    @router.post("/sessions/{session_id}/messages", status_code=status.HTTP_202_ACCEPTED)
    def submit_message(session_id: str, request: MessageRequest) -> dict[str, object]:
        try:
            turn_id, sequence = runner.submit_message(session_id, request.content)
            return {"turnId": turn_id, "accepted": True, "seq": sequence}
        except SessionNotFoundError as exc:
            raise _error(
                "SESSION_NOT_FOUND",
                "Session does not exist in the current workspace.",
                http_status=status.HTTP_404_NOT_FOUND,
            ) from exc
        except TurnConflictError as exc:
            raise _error(
                "TURN_ALREADY_RUNNING",
                str(exc),
                http_status=status.HTTP_409_CONFLICT,
                retryable=True,
            ) from exc

    @router.post("/sessions/{session_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
    def cancel_turn(session_id: str) -> dict[str, object]:
        try:
            accepted = runner.cancel_turn(session_id)
        except SessionNotFoundError as exc:
            raise _error(
                "SESSION_NOT_FOUND",
                "Session does not exist in the current workspace.",
                http_status=status.HTTP_404_NOT_FOUND,
            ) from exc
        return {"accepted": accepted}

    @router.get("/sessions/{session_id}/diff", response_model=DiffResponse)
    def get_diff(session_id: str) -> DiffResponse:
        try:
            runner.snapshot(session_id)
        except SessionNotFoundError as exc:
            raise _error(
                "SESSION_NOT_FOUND",
                "Session does not exist in the current workspace.",
                http_status=status.HTTP_404_NOT_FOUND,
            ) from exc
        return read_workspace_diff(runner.workspace)

    @router.get("/sessions/{session_id}/diff/files/{encoded_path:path}", response_model=DiffPatchResponse)
    def get_diff_file(
        session_id: str,
        encoded_path: str,
        limit: int = Query(default=1_000_000, ge=1, le=MAX_EXPANDED_DIFF_BYTES),
    ) -> DiffPatchResponse:
        try:
            runner.snapshot(session_id)
        except SessionNotFoundError as exc:
            raise _error(
                "SESSION_NOT_FOUND",
                "Session does not exist in the current workspace.",
                http_status=status.HTTP_404_NOT_FOUND,
            ) from exc
        try:
            return read_workspace_diff_file(runner.workspace, encoded_path, max_bytes=limit)
        except FileNotFoundError as exc:
            raise _error(
                "DIFF_FILE_NOT_FOUND",
                "The requested file is not part of the current workspace diff.",
                http_status=status.HTTP_404_NOT_FOUND,
            ) from exc
        except ValueError as exc:
            raise _error(
                "DIFF_PATH_INVALID",
                str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            ) from exc

    @router.post("/permissions/{request_id}/resolve")
    def resolve_permission(
        request_id: str,
        request: PermissionResolveRequest,
    ) -> dict[str, object]:
        try:
            resolved = runner.resolve_permission(
                request_id,
                decision=request.decision,
                feedback=request.feedback,
            )
            return {"resolved": True, "request": resolved}
        except PermissionResolutionError as exc:
            raise _error(
                "PERMISSION_NOT_PENDING",
                str(exc),
                http_status=status.HTTP_409_CONFLICT,
            ) from exc

    @router.websocket("/sessions/{session_id}/events")
    async def session_events(
        websocket: WebSocket,
        session_id: str,
        after: int = Query(default=0, ge=0),
    ) -> None:
        try:
            runner.snapshot(session_id)
        except SessionNotFoundError:
            await websocket.close(code=4404, reason="Session not found")
            return

        await websocket.accept()
        if after > runner.broker.current_seq(session_id):
            # Preserve monotonicity for an in-place reconnect after a server
            # restart, where the browser still owns the previous cursor.
            runner.broker.seed_sequence(session_id, after)
        snapshot_event = runner.publish_snapshot(session_id)
        cursor = after
        disconnect_task = asyncio.create_task(websocket.receive())
        try:
            while True:
                events = await asyncio.to_thread(
                    runner.broker.wait_for_events,
                    session_id,
                    after=cursor,
                    timeout=1.0,
                )
                if disconnect_task.done():
                    message = disconnect_task.result()
                    if message.get("type") == "websocket.disconnect":
                        return
                    # The first-day protocol is server-push only. Reject client
                    # data instead of accepting an unbounded message channel.
                    await websocket.close(code=1003, reason="Client messages are not supported")
                    return
                for event in events:
                    await websocket.send_json(event.to_dict())
                    cursor = event.seq
                if cursor < snapshot_event.seq and not events:
                    cursor = snapshot_event.seq
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            return
        except RuntimeError:
            return
        finally:
            disconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await disconnect_task

    return router
