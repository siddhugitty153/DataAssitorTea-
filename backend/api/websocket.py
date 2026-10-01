"""
WebSocket endpoint — real-time thought streaming for the future Next.js frontend.

The Streamlit MVP uses SSE (/api/threads/{id}/stream), but this WebSocket
endpoint is ready for when you migrate to Next.js.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.routes import threads

ws_router = APIRouter()


class ConnectionManager:
    """Track active WebSocket connections per thread."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, thread_id: str) -> None:
        await ws.accept()
        self._connections.setdefault(thread_id, []).append(ws)

    def disconnect(self, ws: WebSocket, thread_id: str) -> None:
        conns = self._connections.get(thread_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, thread_id: str, data: dict) -> None:
        for ws in self._connections.get(thread_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass


manager = ConnectionManager()


@ws_router.websocket("/ws/{thread_id}")
async def websocket_endpoint(ws: WebSocket, thread_id: str):
    """
    Stream agent thoughts over WebSocket.

    Connect → receive JSON messages as the agent processes → connection closes
    when the thread reaches a terminal state.
    """
    await manager.connect(ws, thread_id)
    try:
        # Wait up to 5 seconds if thread was just being dispatched
        for _ in range(25):
            if thread_id in threads:
                break
            await asyncio.sleep(0.2)

        last_seen = 0
        while True:
            thread = threads.get(thread_id)
            if thread is None:
                await ws.send_json({"error": "Thread not found", "type": "error"})
                break

            thoughts = thread.get("thoughts", [])
            for thought in thoughts[last_seen:]:
                await ws.send_json(thought)
                last_seen += 1

            if thread.get("status") in ("completed", "failed"):
                await ws.send_json(
                    {
                        "type": "done",
                        "status": thread["status"],
                        "result": thread.get("result", ""),
                        "generated_code": thread.get("generated_code", ""),
                        "error": thread.get("error", ""),
                    }
                )
                break

            # Polling delay & listen for client messages
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=0.3)
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws, thread_id)
