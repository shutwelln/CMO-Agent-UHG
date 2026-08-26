"""FastAPI service layer for OpenClaw skills.

Wraps existing CMO Agent infrastructure as HTTP endpoints that OpenClaw
skills can call. Runs on the same VPS as OpenClaw and n8n.

Endpoints:
    POST /api/proofread          — Spelling/grammar correction
    GET  /api/brand-voice/{ws}   — Load workspace brand voice
    POST /api/media/upload       — Upload media to Supabase CDN
    GET  /api/media              — List/search media assets
    POST /api/n8n/execute/{id}   — Trigger n8n workflow
    GET  /api/n8n/workflows      — List n8n workflows
    POST /api/compositions/render — Render Remotion compositions
    POST /api/outreach/append    — Append to outreach Google Sheet
    GET  /health                 — Health check
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

# Add parent project to sys.path so we can import cmo_agent modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cmo_agent.config import get_settings
from cmo_agent.db.database import Database
from cmo_agent.media.storage import MediaStorage
from cmo_agent.n8n.client import N8NClient
from cmo_agent.text.proofreader import Proofreader
from cmo_agent.workspace.brand_voice import BrandVoiceLoader

logger = structlog.get_logger()

app = FastAPI(
    title="CMO Agent Service Layer",
    description="HTTP bridge between OpenClaw skills and CMO Agent infrastructure",
    version="1.0.0",
)

# ── Shared singletons ────────────────────────────────────────────────────

_db: Optional[Database] = None
_storage: Optional[MediaStorage] = None
_n8n: Optional[N8NClient] = None
_proofreader: Optional[Proofreader] = None
_brand_voice_loader: Optional[BrandVoiceLoader] = None


async def _get_db() -> Database:
    global _db
    if _db is None:
        settings = get_settings()
        _db = Database(db_path=settings.db_path)
        await _db.initialize()
    return _db


async def _get_storage() -> MediaStorage:
    global _storage
    if _storage is None:
        settings = get_settings()
        db = await _get_db()
        _storage = MediaStorage(
            db=db,
            supabase_url=settings.supabase_url,
            supabase_service_role_key=settings.supabase_service_role_key,
            supabase_bucket=settings.supabase_bucket,
        )
    return _storage


async def _get_n8n() -> N8NClient:
    global _n8n
    if _n8n is None:
        settings = get_settings()
        _n8n = N8NClient(
            base_url=settings.n8n_base_url,
            api_key=settings.n8n_api_key,
            timeout=settings.n8n_timeout,
            max_retries=settings.n8n_max_retries,
        )
    return _n8n


async def _get_proofreader() -> Proofreader:
    global _proofreader
    if _proofreader is None:
        from cmo_agent.llm.anthropic import AnthropicLLM

        settings = get_settings()
        scanning_llm = AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model_scanning,
            max_tokens=settings.llm_max_tokens,
        )
        _proofreader = Proofreader(llm=scanning_llm)
    return _proofreader


def _get_brand_voice_loader() -> BrandVoiceLoader:
    global _brand_voice_loader
    if _brand_voice_loader is None:
        settings = get_settings()
        _brand_voice_loader = BrandVoiceLoader(
            base_dir=Path(settings.brand_voices_dir)
        )
    return _brand_voice_loader


# ── Health check ──────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check with component status."""
    settings = get_settings()
    components = {
        "service": "ok",
        "n8n_configured": bool(settings.n8n_api_key),
        "supabase_configured": bool(settings.supabase_url),
        "anthropic_configured": bool(settings.anthropic_api_key),
    }

    # Test n8n connectivity
    if settings.n8n_api_key:
        try:
            n8n = await _get_n8n()
            components["n8n_reachable"] = await n8n.health_check()
        except Exception:
            components["n8n_reachable"] = False

    return {"status": "ok", "service": "cmo-agent-service-layer", "components": components}


# ── Proofreading ──────────────────────────────────────────────────────────


class ProofreadRequest(BaseModel):
    text: str
    preserve_terms: Optional[List[str]] = None
    context: str = ""


class ProofreadResponse(BaseModel):
    corrected_text: str
    corrections: List[Dict[str, str]]
    has_corrections: bool


@app.post("/api/proofread", response_model=ProofreadResponse)
async def proofread(request: ProofreadRequest):
    """Proofread text with brand term preservation."""
    try:
        proofreader = await _get_proofreader()
        result = await proofreader.proofread(
            text=request.text,
            preserve_terms=request.preserve_terms,
            context=request.context,
        )
        return ProofreadResponse(
            corrected_text=result.corrected_text,
            corrections=result.corrections,
            has_corrections=result.has_corrections,
        )
    except Exception as e:
        logger.error("proofread_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Brand voice ───────────────────────────────────────────────────────────


@app.get("/api/brand-voice/{workspace_id}")
async def get_brand_voice(workspace_id: str):
    """Load brand voice for a workspace."""
    loader = _get_brand_voice_loader()
    filename = f"{workspace_id}.txt"

    if not loader.exists(filename):
        raise HTTPException(
            status_code=404,
            detail=f"Brand voice not found for workspace '{workspace_id}'",
        )

    try:
        voice = loader.load(filename)
        return {"workspace_id": workspace_id, "brand_voice": voice}
    except Exception as e:
        logger.error("brand_voice_error", workspace_id=workspace_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/brand-voice")
async def list_brand_voices():
    """List available brand voice workspaces."""
    loader = _get_brand_voice_loader()
    voices = []
    for f in loader.base_dir.glob("*.txt"):
        voices.append(f.stem)
    return {"workspaces": sorted(voices)}


# ── Media upload ──────────────────────────────────────────────────────────


@app.post("/api/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    workspace_id: str = Form("saverwell"),
    media_type: str = Form("image"),
    source_agent: str = Form("openclaw"),
    prompt: Optional[str] = Form(None),
):
    """Upload media to Supabase CDN with DB tracking."""
    try:
        storage = await _get_storage()
        data = await file.read()

        # Detect extension from filename
        ext = Path(file.filename or "file.bin").suffix.lstrip(".")
        if not ext:
            ext = "bin"

        asset = await storage.upload(
            data=data,
            workspace_id=workspace_id,
            media_type=media_type,
            extension=ext,
            source_agent=source_agent,
            prompt=prompt,
        )
        return {
            "status": "uploaded",
            "asset_id": asset.id,
            "cdn_url": asset.cdn_url,
            "local_path": asset.local_path,
        }
    except Exception as e:
        logger.error("media_upload_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/media/upload-base64")
async def upload_media_base64(
    data_b64: str = Form(...),
    filename: str = Form("file.png"),
    workspace_id: str = Form("saverwell"),
    media_type: str = Form("image"),
    source_agent: str = Form("openclaw"),
    prompt: Optional[str] = Form(None),
):
    """Upload base64-encoded media (for skill scripts that can't multipart)."""
    try:
        storage = await _get_storage()
        data = base64.b64decode(data_b64)
        ext = Path(filename).suffix.lstrip(".") or "bin"

        asset = await storage.upload(
            data=data,
            workspace_id=workspace_id,
            media_type=media_type,
            extension=ext,
            source_agent=source_agent,
            prompt=prompt,
        )
        return {
            "status": "uploaded",
            "asset_id": asset.id,
            "cdn_url": asset.cdn_url,
            "local_path": asset.local_path,
        }
    except Exception as e:
        logger.error("media_upload_b64_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/media")
async def list_media(
    workspace_id: str = "saverwell",
    media_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
):
    """Browse media library."""
    try:
        storage = await _get_storage()
        if search:
            assets = await storage.search_assets(workspace_id, search, limit)
        else:
            assets = await storage.list_assets(workspace_id, media_type, limit)
        return {
            "assets": [a.model_dump(mode="json") for a in assets],
            "count": len(assets),
        }
    except Exception as e:
        logger.error("media_list_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── n8n workflow execution ────────────────────────────────────────────────


class N8NExecuteRequest(BaseModel):
    data: Optional[Dict[str, Any]] = None


@app.post("/api/n8n/execute/{workflow_id}")
async def execute_n8n_workflow(workflow_id: str, request: N8NExecuteRequest):
    """Trigger an n8n workflow by ID."""
    try:
        n8n = await _get_n8n()
        execution = await n8n.execute_workflow(workflow_id, data=request.data)
        return {
            "status": "executed",
            "execution_id": execution.id,
            "workflow_id": workflow_id,
            "data": execution.data if hasattr(execution, "data") else None,
        }
    except Exception as e:
        logger.error("n8n_execute_error", workflow_id=workflow_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/n8n/workflows")
async def list_n8n_workflows(active: Optional[bool] = None):
    """List available n8n workflows."""
    try:
        n8n = await _get_n8n()
        result = await n8n.list_workflows(active=active)
        workflows = []
        for wf in result.data:
            workflows.append({
                "id": wf.id,
                "name": wf.name,
                "active": wf.active,
            })
        return {"workflows": workflows, "count": len(workflows)}
    except Exception as e:
        logger.error("n8n_list_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/n8n/workflow/{workflow_id}")
async def get_n8n_workflow(workflow_id: str):
    """Get details for a specific n8n workflow."""
    try:
        n8n = await _get_n8n()
        wf = await n8n.get_workflow(workflow_id)
        return {
            "id": wf.id,
            "name": wf.name,
            "active": wf.active,
            "nodes": len(wf.nodes) if hasattr(wf, "nodes") else 0,
        }
    except Exception as e:
        logger.error("n8n_get_error", workflow_id=workflow_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Composition rendering ────────────────────────────────────────────────


class CompositionRenderRequest(BaseModel):
    template: str  # e.g. "StaticLayout", "HeroOverlay", "QuoteCard"
    props: Dict[str, Any]  # Template-specific props
    output_format: str = "png"  # "png" or "mp4"
    workspace_id: str = "saverwell"


@app.post("/api/compositions/render")
async def render_composition(request: CompositionRenderRequest):
    """Render a Remotion composition template."""
    try:
        from cmo_agent.text.composition_renderer import CompositionRenderer

        settings = get_settings()
        renderer = CompositionRenderer(
            remotion_dir=settings.remotion_project_dir,
            output_dir="./data/compositions",
        )

        if request.output_format == "mp4":
            result = await renderer.render_motion(
                template=request.template,
                props=request.props,
            )
        else:
            result = await renderer.render_still(
                template=request.template,
                props=request.props,
            )

        # Upload to CDN if configured
        storage = await _get_storage()
        if storage.is_configured and result.get("output_path"):
            asset = await storage.upload_from_file(
                file_path=result["output_path"],
                workspace_id=request.workspace_id,
                media_type="composition",
                source_agent="openclaw_composition",
                prompt=f"Template: {request.template}",
            )
            result["cdn_url"] = asset.cdn_url
            result["asset_id"] = asset.id

        return result
    except Exception as e:
        logger.error("composition_render_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Outreach dashboard ───────────────────────────────────────────────────


class OutreachAppendRequest(BaseModel):
    rows: List[Dict[str, Any]]
    spreadsheet_id: Optional[str] = None


@app.post("/api/outreach/append")
async def append_outreach(request: OutreachAppendRequest):
    """Append rows to the outreach Google Sheet dashboard."""
    try:
        from cmo_agent.outreach.dashboard import OutreachDashboard

        settings = get_settings()
        sheet_id = request.spreadsheet_id or settings.outreach_spreadsheet_id
        if not sheet_id:
            raise HTTPException(
                status_code=400,
                detail="No spreadsheet_id provided and OUTREACH_SPREADSHEET_ID not configured",
            )

        dashboard = OutreachDashboard(
            credentials_path=settings.google_credentials_path,
            spreadsheet_id=sheet_id,
        )
        count = await dashboard.append_rows(request.rows)
        return {"status": "appended", "rows_added": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("outreach_append_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Shutdown ──────────────────────────────────────────────────────────────


@app.on_event("shutdown")
async def shutdown():
    """Cleanup shared resources."""
    global _db, _n8n, _storage
    if _n8n:
        await _n8n.close()
        _n8n = None
    if _db:
        await _db.close()
        _db = None
    _storage = None
    logger.info("service_layer_shutdown")
