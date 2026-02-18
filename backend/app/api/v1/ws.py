import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.core.security import validate_ws_ticket
from app.core.stream import subscribe_project
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per project."""

    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, project_id: int, websocket: WebSocket):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)

    def disconnect(self, project_id: int, websocket: WebSocket):
        if project_id in self.active_connections:
            self.active_connections[project_id].remove(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]

    async def broadcast(self, project_id: int, message: dict):
        """Broadcast event to all connected clients for a project."""
        if project_id not in self.active_connections:
            return
        dead = []
        for connection in self.active_connections[project_id]:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for conn in dead:
            self.disconnect(project_id, conn)


manager = ConnectionManager()


async def _listen_pubsub(project_id: int, websocket: WebSocket, redis: Redis) -> None:
    """Subscribe to Redis pub/sub and forward messages to WebSocket.

    Silently exits if Redis pub/sub is unavailable (falls back to in-memory only).
    """
    pubsub, channel = await subscribe_project(project_id, redis=redis)
    if pubsub is None:
        # Redis pub/sub unavailable — rely on in-memory broadcast only
        logger.debug("Redis pub/sub unavailable for project %d, using in-memory only", project_id)
        return

    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                try:
                    data = json.loads(msg["data"])
                    await websocket.send_json(data)
                except Exception:
                    break
            await asyncio.sleep(0.05)
    except Exception:
        pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass


@router.websocket("/events/{project_id}")
async def websocket_events(
    websocket: WebSocket,
    project_id: int,
    ticket: str | None = None,
):
    """WebSocket endpoint for live event streaming.

    Connect with: ws://host/api/v1/ws/events/{project_id}?ticket=<ticket>

    Uses short-lived single-use tickets (issued via POST /auth/ws-ticket)
    instead of JWTs in the query string. Redis pub/sub for cross-process
    fan-out when available, with in-memory ConnectionManager as fallback.
    """
    if not ticket:
        await websocket.close(code=4001, reason="Missing ticket")
        return

    # Get Redis from app.state (same as DI but manual for WebSocket)
    redis: Redis = websocket.app.state.redis  # type: ignore[assignment]

    # Validate and consume the ticket (single-use)
    user_id = await validate_ws_ticket(ticket, redis=redis)
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid or expired ticket")
        return

    # Verify project access
    async with websocket.app.state._db_sessionmaker() as db:  # type: ignore[union-attr]
        project_service = ProjectService(db)
        try:
            await project_service.get(project_id=project_id, user_id=user_id)
        except Exception:
            await websocket.close(code=4003, reason="Project not found")
            return

    await manager.connect(project_id, websocket)

    # Start pub/sub listener as a background task
    pubsub_task = asyncio.create_task(_listen_pubsub(project_id, websocket, redis))

    try:
        while True:
            # Keep connection alive, client sends pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
        pubsub_task.cancel()
        try:
            await pubsub_task
        except asyncio.CancelledError:
            pass
