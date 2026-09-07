from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.manager import ConnectionManager

router = APIRouter()


def build_ws_router(manager: ConnectionManager) -> APIRouter:
    @router.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            while True:
                # Clients don't need to send anything; we just need the
                # receive loop alive to detect disconnects promptly.
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return router
