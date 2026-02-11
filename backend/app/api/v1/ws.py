import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, is_access_token_revoked
from app.services.project_service import ProjectService
from app.services.user_service import UserService

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


async def _authenticate_ws(token: str, db: AsyncSession) -> int | None:
    """Authenticate WebSocket connection, returns user_id or None."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        return None
    if await is_access_token_revoked(jti):
        return None
    service = UserService(db)
    user = await service.get(int(user_id))
    if not user or not user.is_active:
        return None
    return user.id


@router.websocket("/events/{project_id}")
async def websocket_events(
    websocket: WebSocket,
    project_id: int,
    token: str | None = None,
):
    """WebSocket endpoint for live event streaming.

    Connect with: ws://host/api/v1/ws/events/{project_id}?token=<jwt>
    """
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    async with websocket.app.state._db_sessionmaker() as db:  # type: ignore[union-attr]
        user_id = await _authenticate_ws(token, db)
        if user_id is None:
            await websocket.close(code=4001, reason="Invalid token")
            return

        # Verify project access
        project_service = ProjectService(db)
        try:
            await project_service.get(project_id=project_id, user_id=user_id)
        except Exception:
            await websocket.close(code=4003, reason="Project not found")
            return

    await manager.connect(project_id, websocket)
    try:
        while True:
            # Keep connection alive, client sends pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
