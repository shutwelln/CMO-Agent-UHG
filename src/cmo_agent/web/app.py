"""FastAPI application for CMO Agent Web UI."""

from __future__ import annotations

import os
from typing import Dict, List, Optional
from uuid import uuid4

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import get_settings
from ..db.database import Database
from ..media.storage import MediaStorage
from ..runtime.session import CMOSession

logger = structlog.get_logger()

app = FastAPI(
    title="CMO Agent",
    description="AI-Powered Marketing Automation Agent",
    version="0.1.0",
)

# Session storage (in-memory for local development)
sessions: Dict[str, CMOSession] = {}


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    reply: str
    status: str
    trace_id: str
    session_id: str
    artifacts: List[dict] = []
    actions_taken: List[str] = []


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "cmo-agent"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a chat message and return agent response."""
    session_id = request.session_id or str(uuid4())

    # Get or create session
    if session_id not in sessions:
        sessions[session_id] = CMOSession(session_id=session_id)
        logger.info("web_session_created", session_id=session_id)

    session = sessions[session_id]

    try:
        response = await session.ask(request.message)

        return ChatResponse(
            reply=response.text,
            status=response.status,
            trace_id=response.trace_id,
            session_id=session_id,
            artifacts=response.artifacts,
            actions_taken=response.actions_taken,
        )
    except Exception as e:
        logger.error("web_chat_error", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and cleanup resources."""
    if session_id in sessions:
        await sessions[session_id].close()
        del sessions[session_id]
        logger.info("web_session_deleted", session_id=session_id)
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup all sessions on shutdown."""
    logger.info("web_shutdown", session_count=len(sessions))
    for session_id, session in sessions.items():
        try:
            await session.close()
        except Exception as e:
            logger.error("web_session_close_error", session_id=session_id, error=str(e))
    sessions.clear()


# ── Media library API ─────────────────────────────────────────────────────


@app.get("/api/media")
async def list_media(
    workspace_id: str = "uhg",
    media_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
):
    """Browse media library — returns list of assets with CDN URLs."""
    settings = get_settings()
    db = Database(db_path=settings.db_path)
    await db.initialize()
    try:
        storage = MediaStorage(
            db=db,
            supabase_url=settings.supabase_url,
            supabase_service_role_key=settings.supabase_service_role_key,
            supabase_bucket=settings.supabase_bucket,
        )
        if search:
            assets = await storage.search_assets(workspace_id, search, limit)
        else:
            assets = await storage.list_assets(workspace_id, media_type, limit)
        return {
            "assets": [a.model_dump(mode="json") for a in assets],
            "count": len(assets),
        }
    finally:
        await db.close()


# Static files setup
static_dir = os.path.join(os.path.dirname(__file__), "static")


@app.get("/")
async def index():
    """Serve the main UI page."""
    return FileResponse(os.path.join(static_dir, "index.html"))


# Mount static files (CSS, JS)
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
