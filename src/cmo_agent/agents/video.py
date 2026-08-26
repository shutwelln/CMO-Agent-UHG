"""Video Agent - video generation for marketing content."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import structlog

from ..db.database import Database
from ..db.repositories import DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality.visual_spec import VisualSpecRefiner, VideoSpec
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# ── Quality tier configuration ───────────────────────────────────────────

_QUALITY_TIERS: Dict[str, Dict[str, Any]] = {
    "low": {
        "provider": "fal.ai",
        "model": "kling-video/v2.1/master/text-to-video",
        "model_i2v": "kling-video/v2.1/master/image-to-video",
        "approx_cost": "$0.10-0.30 per 5s clip",
        "resolution": "1080p",
        "max_duration": 10,
        "poll_timeout": 180,
        "description": "High-quality video via fal.ai (Kling 2.1 Master). Great for drafts, social media clips, and concept validation.",
    },
    "medium": {
        "provider": "fal.ai",
        "model": "kling-video/v2.6/pro/text-to-video",
        "model_i2v": "kling-video/v2.6/pro/image-to-video",
        "approx_cost": "$0.35-0.60 per 5s clip",
        "resolution": "1080p",
        "max_duration": 10,
        "poll_timeout": 240,
        "description": "Premium video via fal.ai (Kling 2.6 Pro) with audio. Best fal.ai tier for polished marketing videos.",
    },
    "high": {
        "provider": "OpenAI Sora",
        "model": "sora-2",
        "approx_cost": "$2.00-5.00 per 5-20s clip",
        "resolution": "1080p",
        "max_duration": 20,
        "poll_timeout": 360,
        "description": "Premium video via OpenAI Sora 2. Best for hero content, ads, and high-production marketing videos.",
    },
}

_POLL_INTERVAL_SECONDS = 5

# Signals that indicate the video content legitimately needs text/labels
_VIDEO_TEXT_SIGNALS = frozenset(
    {
        "infographic",
        "diagram",
        "data viz",
        "dashboard",
        "chart",
        "animated text",
        "kinetic typography",
        "title sequence",
        "lower third",
        "text animation",
        "motion graphic",
        "scorecard",
        "metrics",
        "kpi",
    }
)


class VideoAgent(BaseAgent):
    """Generates marketing video concepts, scripts, and AI-generated videos.

    Provides:
    - Video script generation in brand voice
    - Storyboard descriptions for production
    - Platform-optimized video concepts
    - Shot list generation
    - AI video generation with tiered pricing (fal.ai / Sora)
    """

    agent_id = "video_agent"
    agent_name = "Video Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        fal_api_key: str = "",
        openai_api_key: str = "",
        video_output_dir: str = "./data/videos",
        media_storage: Optional[Any] = None,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._workspace_mgr = workspace_manager
        self._fal_api_key = fal_api_key
        self._openai_api_key = openai_api_key
        self._video_output_dir = video_output_dir
        self._media_storage = media_storage
        self._scanning_llm = scanning_llm
        self._spec_refiner = VisualSpecRefiner(generation_llm=llm, critique_llm=scanning_llm)
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def _tier_available(self, tier: str) -> bool:
        """Check if the API key for a tier is configured."""
        if tier in ("low", "medium"):
            return bool(self._fal_api_key)
        if tier == "high":
            return bool(self._openai_api_key)
        return False

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        ws_label = workspace_id or "all workspaces"

        available = []
        for tier_name, tier_cfg in _QUALITY_TIERS.items():
            status = "AVAILABLE" if self._tier_available(tier_name) else "not configured"
            available.append(
                f"  - {tier_name.upper()} ({tier_cfg['provider']}): {status} — {tier_cfg['approx_cost']}"
            )
        tiers_text = "\n".join(available)

        return f"""You are the Video Agent for {ws_label}.
You create marketing video concepts, scripts, storyboards, and AI-generated videos.

You can:
- Write video scripts optimized for specific platforms
- Create storyboard descriptions with shot-by-shot breakdowns
- Suggest video concepts based on content and brand voice
- Generate shot lists for production
- Generate AI videos using tiered pricing (fal.ai Kling, OpenAI Sora)

AI Video Generation Tiers:
{tiers_text}

IMPORTANT: When asked to generate a video, ALWAYS call get_video_pricing first to show
the user available tiers and costs. Wait for the user to choose a tier before calling
generate_video.

When creating video content:
- Match the brand voice and tone
- Keep scripts concise (most social videos are 15-60 seconds)
- Include visual direction and on-screen text cues
- Optimize for the target platform format

Standard video formats:
- Instagram Reel / TikTok: 9:16 vertical, 15-60s
- YouTube Short: 9:16 vertical, up to 60s
- YouTube standard: 16:9 horizontal, 2-10 min
- LinkedIn video: 16:9 or 1:1, 30s-2 min
- Facebook/Twitter video: 16:9 or 1:1, 15s-2 min
- Story format: 9:16 vertical, 15s segments"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="create_video_script",
            description=(
                "Write a video script for a marketing topic. Includes narration, "
                "visual directions, and timing. Specify platform and duration."
            ),
        )
        async def create_video_script(
            topic: str,
            workspace_id: str,
            platform: str = "instagram_reel",
            duration_seconds: int = 30,
            style: str = "educational",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            reference_docs = await self._workspace_mgr.get_reference_docs(workspace_id)
            format_info = _get_format_info(platform)

            ref_docs_section = ""
            if reference_docs:
                ref_docs_section = f"""
Reference documents (use real data, metrics, and facts from these):
{reference_docs[:10000]}
"""

            prompt = f"""Write a {duration_seconds}-second video script for:
Topic: {topic}
Platform: {platform}
Style: {style}

Format: {format_info}

Brand context:
{brand_voice[:400] if brand_voice else "No brand voice specified."}
{ref_docs_section}

Structure the script with:
1. HOOK (first 3 seconds) - grab attention immediately
2. BODY - deliver the main message
3. CTA - clear call to action

For each segment provide:
- TIME: Timestamp range (e.g., 0:00-0:03)
- NARRATION: What is said (voiceover or on-camera)
- VISUAL: What appears on screen
- TEXT: Any on-screen text/captions
- MUSIC/SFX: Audio direction

Return as a JSON object with keys: title, platform, duration, hook, segments (array), cta, notes"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            try:
                script = json.loads(response.content)
            except (json.JSONDecodeError, TypeError):
                script = {
                    "title": topic,
                    "platform": platform,
                    "duration": duration_seconds,
                    "raw_script": response.content,
                }

            return {
                "script": script,
                "platform": platform,
                "duration_seconds": duration_seconds,
                "style": style,
            }

        @self.tool_registry.register(
            name="create_storyboard",
            description=(
                "Create a storyboard with shot-by-shot visual descriptions "
                "for a video concept. Returns detailed shot descriptions."
            ),
        )
        async def create_storyboard(
            concept: str,
            workspace_id: str,
            num_shots: int = 6,
            platform: str = "instagram_reel",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a {num_shots}-shot storyboard for this video concept:

CONCEPT: {concept}
PLATFORM: {platform}

BRAND CONTEXT:
{brand_voice[:300] if brand_voice else "No brand voice specified."}

For each shot provide:
1. Shot number
2. Duration (seconds)
3. Camera angle/movement (e.g., close-up, wide shot, pan left)
4. Visual description (what's in frame)
5. On-screen text (if any)
6. Audio (narration, music, sound effects)
7. Transition to next shot

Return as a JSON object with keys: title, platform, total_duration, shots (array of objects)"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            try:
                storyboard = json.loads(response.content)
            except (json.JSONDecodeError, TypeError):
                storyboard = {
                    "title": concept,
                    "raw_storyboard": response.content,
                }

            return {
                "storyboard": storyboard,
                "platform": platform,
                "num_shots": num_shots,
            }

        @self.tool_registry.register(
            name="suggest_video_concepts",
            description=(
                "Suggest video ideas for a marketing topic or campaign. "
                "Returns concepts with format, duration, and platform recommendations."
            ),
        )
        async def suggest_video_concepts(
            content: str,
            workspace_id: str,
            count: int = 3,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Suggest {count} video concepts for this marketing content.

CONTENT:
{content[:1000]}

BRAND CONTEXT:
{brand_voice[:300] if brand_voice else "No brand voice specified."}

For each suggestion provide:
1. Title
2. Brief description of the video
3. Recommended platform (instagram_reel, youtube_short, linkedin, etc.)
4. Recommended duration in seconds
5. Style (educational, testimonial, behind-the-scenes, product-demo, storytelling)
6. Why this concept works for the brand

Return as a JSON array of objects with keys: title, description, platform, duration, style, rationale"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.8,
            )

            try:
                concepts = json.loads(response.content)
            except (json.JSONDecodeError, TypeError):
                concepts = [{"title": "Parse error", "description": response.content}]

            return {"concepts": concepts, "count": len(concepts)}

        @self.tool_registry.register(
            name="create_shot_list",
            description=(
                "Generate a production shot list from a video script. "
                "Useful for planning a video shoot."
            ),
        )
        async def create_shot_list(
            script_summary: str,
            workspace_id: str,
            location: str = "studio",
        ) -> Dict[str, Any]:
            prompt = f"""Create a production shot list for this video:

SCRIPT SUMMARY:
{script_summary[:1000]}

LOCATION: {location}

For each shot include:
- Shot number
- Setup description (camera, lighting, props)
- Subject/talent direction
- Duration
- Notes for editor

Also include:
- Equipment recommendations
- Estimated total shoot time
- Any props or assets needed

Return as a JSON object with keys: shots (array), equipment, estimated_shoot_minutes, props_needed"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            try:
                shot_list = json.loads(response.content)
            except (json.JSONDecodeError, TypeError):
                shot_list = {"raw_shot_list": response.content}

            return {
                "shot_list": shot_list,
                "location": location,
            }

        @self.tool_registry.register(
            name="get_video_pricing",
            description=(
                "Show available AI video generation tiers with pricing, resolution, "
                "and availability. Call this BEFORE generate_video so the user can "
                "choose a tier. No API call is made."
            ),
        )
        async def get_video_pricing() -> Dict[str, Any]:
            tiers = []
            for tier_name, cfg in _QUALITY_TIERS.items():
                tiers.append(
                    {
                        "tier": tier_name,
                        "provider": cfg["provider"],
                        "model": cfg["model"],
                        "approx_cost": cfg["approx_cost"],
                        "resolution": cfg["resolution"],
                        "max_duration_seconds": cfg["max_duration"],
                        "available": self._tier_available(tier_name),
                        "description": cfg["description"],
                    }
                )
            return {
                "tiers": tiers,
                "instructions": "Present these options to the user and ask them to choose a tier before calling generate_video.",
            }

        @self.tool_registry.register(
            name="generate_video",
            description=(
                "Generate a video using an AI provider. Requires a quality tier "
                "(low/medium/high), prompt, workspace_id, and optional parameters. "
                "Call get_video_pricing first to show the user available tiers."
            ),
        )
        async def generate_video(
            prompt: str,
            workspace_id: str,
            quality: str = "low",
            duration_seconds: int = 5,
            aspect_ratio: str = "9:16",
            image_url: Optional[str] = None,
        ) -> Dict[str, Any]:
            quality = quality.lower()
            if quality not in _QUALITY_TIERS:
                return {
                    "error": f"Invalid quality tier '{quality}'. Choose from: low, medium, high.",
                    "status": "failed",
                }

            if not self._tier_available(quality):
                tier_cfg = _QUALITY_TIERS[quality]
                key_names = {
                    "low": "FAL_API_KEY",
                    "medium": "FAL_API_KEY",
                    "high": "OPENAI_API_KEY",
                }
                return {
                    "error": f"{tier_cfg['provider']} is not configured. Set {key_names[quality]} in .env.",
                    "status": "not_configured",
                }

            tier_cfg = _QUALITY_TIERS[quality]

            # Load brand voice and optimize prompt for the provider
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            optimized_prompt = await _optimize_video_prompt(
                llm=self.llm,
                user_prompt=prompt,
                brand_voice=brand_voice,
                provider=tier_cfg["provider"],
                spec_refiner=self._spec_refiner,
            )

            logger.info(
                "video_generation_started",
                tier=quality,
                provider=tier_cfg["provider"],
                approx_cost=tier_cfg["approx_cost"],
                duration=duration_seconds,
                aspect_ratio=aspect_ratio,
                has_image_url=image_url is not None,
            )

            try:
                # Call the appropriate provider
                if quality in ("low", "medium"):
                    result = await _call_fal_video(
                        api_key=self._fal_api_key,
                        prompt=optimized_prompt,
                        model=tier_cfg["model"],
                        model_i2v=tier_cfg.get("model_i2v", ""),
                        duration_seconds=duration_seconds,
                        aspect_ratio=aspect_ratio,
                        image_url=image_url,
                        poll_timeout=tier_cfg["poll_timeout"],
                    )
                else:
                    result = await _call_sora_video(
                        api_key=self._openai_api_key,
                        prompt=optimized_prompt,
                        duration_seconds=duration_seconds,
                        aspect_ratio=aspect_ratio,
                        poll_timeout=tier_cfg["poll_timeout"],
                    )

                # Download the video to persist beyond temporary URLs
                video_url = result["url"]
                download_headers = result.get("auth_headers")
                local_path = await _download_video(
                    url=video_url,
                    output_dir=self._video_output_dir,
                    headers=download_headers,
                )

                # Upload to Supabase if available
                cdn_url = video_url
                asset_id = None
                if self._media_storage:
                    try:
                        asset = await self._media_storage.upload_from_file(
                            file_path=str(local_path),
                            workspace_id=workspace_id,
                            media_type="video",
                            source_agent=self.agent_id,
                            prompt=prompt,
                            metadata={
                                "provider": tier_cfg["provider"],
                                "model": tier_cfg["model"],
                                "duration": duration_seconds,
                                "aspect_ratio": aspect_ratio,
                            },
                        )
                        cdn_url = asset.cdn_url or video_url
                        asset_id = asset.id
                    except Exception as e:
                        logger.warning("video_media_upload_failed", error=str(e))

                # Save as draft
                body = json.dumps(
                    {
                        "video_url": cdn_url,
                        "temp_url": video_url,
                        "local_path": str(local_path),
                        "provider": tier_cfg["provider"],
                        "model": tier_cfg["model"],
                        "prompt": optimized_prompt,
                        "original_prompt": prompt,
                        "duration_seconds": duration_seconds,
                        "aspect_ratio": aspect_ratio,
                        "metadata": result.get("metadata", {}),
                    }
                )
                draft = await self._drafts.create(
                    workspace_id=workspace_id,
                    content_type="video",
                    title=f"AI Video: {prompt[:60]}",
                    body=body,
                )

                # Link media asset to draft
                if asset_id and self._media_storage:
                    try:
                        await self._media_storage.link_to_draft(asset_id, draft.id)
                    except Exception as e:
                        logger.warning("media_link_to_draft_failed", error=str(e))

                logger.info(
                    "video_generation_completed",
                    tier=quality,
                    provider=tier_cfg["provider"],
                    approx_cost=tier_cfg["approx_cost"],
                    draft_id=draft.id,
                    local_path=str(local_path),
                )

                return {
                    "status": "generated",
                    "video_url": cdn_url,
                    "local_path": str(local_path),
                    "draft_id": draft.id,
                    "provider": tier_cfg["provider"],
                    "approx_cost": tier_cfg["approx_cost"],
                    "prompt_used": optimized_prompt,
                    "asset_id": asset_id,
                }

            except TimeoutError:
                logger.error(
                    "video_generation_timeout",
                    tier=quality,
                    provider=tier_cfg["provider"],
                    timeout=tier_cfg["poll_timeout"],
                )
                return {
                    "error": f"Video generation timed out after {tier_cfg['poll_timeout']}s. The provider may be under heavy load — try again later.",
                    "status": "timeout",
                }
            except Exception as e:
                logger.error(
                    "video_generation_failed",
                    tier=quality,
                    provider=tier_cfg["provider"],
                    error=str(e),
                )
                return {
                    "error": f"Video generation failed: {e}",
                    "status": "failed",
                }


# ── Helper functions ──────────────────────────────────────────────────────


def _get_format_info(platform: str) -> str:
    """Return format guidance for a video platform."""
    formats = {
        "instagram_reel": "Vertical 9:16, 15-90 seconds. Fast-paced, hook in first 3s. Captions essential.",
        "tiktok": "Vertical 9:16, 15-60 seconds. Trending sounds, authentic style. Hook immediately.",
        "youtube_short": "Vertical 9:16, up to 60 seconds. Loopable content performs well.",
        "youtube": "Horizontal 16:9, 2-10 minutes. Strong intro, value-packed, end screen CTA.",
        "linkedin": "16:9 or 1:1, 30s-2 min. Professional tone. Captions required (85% watch muted).",
        "facebook": "16:9 or 1:1, 15s-2 min. Captions essential. Emotional hooks work well.",
        "twitter": "16:9 or 1:1, 15s-2 min. Concise, punchy. Autoplay without sound.",
        "story": "Vertical 9:16, 15-second segments. Swipe-up CTA. Casual and immediate.",
    }
    return formats.get(
        platform.lower(), "Standard video format. Keep it professional and engaging."
    )


async def _optimize_video_prompt(
    llm: BaseLLM,
    user_prompt: str,
    brand_voice: str,
    provider: str,
    spec_refiner: Optional[VisualSpecRefiner] = None,
) -> str:
    """Use structured VideoSpec to generate a provider-optimized video prompt."""
    if spec_refiner:
        try:
            spec_dict = await spec_refiner.generate_spec(
                user_description=user_prompt,
                brand_voice=brand_voice,
                spec_type="video",
            )
            if spec_dict:
                spec_dict = await spec_refiner.refine_spec(
                    spec=spec_dict,
                    brand_voice=brand_voice,
                )
                # Convert spec to prompt
                try:
                    video_spec = VideoSpec(**spec_dict)
                except Exception:
                    video_spec = None

                if video_spec:
                    parts = [video_spec.scene_description]
                    if video_spec.camera_movement != "static":
                        parts.append(f"camera: {video_spec.camera_movement}")
                    parts.append(f"{video_spec.lighting} lighting")
                    parts.append(f"{video_spec.color_grade} color grade")
                    parts.append(f"{video_spec.pacing} pacing")
                    prompt_text = ", ".join(parts)
                    if len(prompt_text) > 500:
                        prompt_text = prompt_text[:497] + "..."
                    return prompt_text
        except Exception as e:
            logger.warning("video_spec_generation_failed", error=str(e))

    # Fallback to legacy prompt optimization
    lower_prompt = user_prompt.lower()
    needs_text = any(signal in lower_prompt for signal in _VIDEO_TEXT_SIGNALS)

    if needs_text:
        text_rule = "- Text overlays and labels ARE expected for this content. Describe text placement, size, animation, and readability."
    else:
        text_rule = "- Do not include text overlays (AI video handles text poorly)"

    prompt = f"""Optimize this video generation prompt for {provider}.

USER PROMPT: {user_prompt}

BRAND CONTEXT:
{brand_voice[:300] if brand_voice else "No brand voice specified."}

RULES:
- Keep it under 500 characters
- Be specific about motion, camera movement, lighting, and style
{text_rule}
- Tailor the language to what {provider} responds to best
- Maintain the brand tone

Return ONLY the optimized prompt, nothing else."""

    response = await llm.complete(
        messages=[Message(role="user", content=prompt)],
        temperature=0.6,
    )
    return response.content.strip()


async def _poll_for_completion(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    poll_timeout: int,
    status_field: str = "status",
    completed_statuses: Optional[List[str]] = None,
    failed_statuses: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Poll an async job endpoint until completion or timeout."""
    completed = completed_statuses or ["completed", "COMPLETED", "succeeded", "SUCCEEDED"]
    failed = failed_statuses or ["failed", "FAILED", "error", "ERROR"]
    elapsed = 0

    while elapsed < poll_timeout:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        status = data.get(status_field, "")

        if status in completed:
            return data
        if status in failed:
            error_msg = data.get("error", data.get("message", "Unknown error"))
            raise RuntimeError(f"Video generation failed: {error_msg}")

        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS

    raise TimeoutError(f"Polling timed out after {poll_timeout}s")


async def _call_fal_video(
    api_key: str,
    prompt: str,
    model: str = "kling-video/v2.1/master/text-to-video",
    model_i2v: str = "kling-video/v2.1/master/image-to-video",
    duration_seconds: int = 5,
    aspect_ratio: str = "9:16",
    image_url: Optional[str] = None,
    poll_timeout: int = 180,
) -> Dict[str, Any]:
    """Submit a video generation job to fal.ai and poll for result.

    Uses the fal.ai Queue API:
      POST  https://queue.fal.run/fal-ai/{model}  → submit job
      GET   {status_url}                           → poll status
      GET   {response_url}                         → fetch result

    Kling models expect duration as a string ("5" or "10") and
    aspect_ratio as "16:9", "9:16", or "1:1".
    """
    # Use image-to-video model when an image reference is provided
    active_model = model_i2v if (image_url and model_i2v) else model
    submit_url = f"https://queue.fal.run/fal-ai/{active_model}"
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }

    # Kling expects duration as a string ("5" or "10"), clamped to 10s max
    duration_str = str(min(duration_seconds, 10))
    payload: Dict[str, Any] = {
        "prompt": prompt,
        "duration": duration_str,
        "aspect_ratio": aspect_ratio,
    }
    if image_url:
        payload["image_url"] = image_url

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Submit the job
        resp = await client.post(submit_url, headers=headers, json=payload)
        resp.raise_for_status()
        job = resp.json()

        status_url = job.get("status_url", "")
        response_url = job.get("response_url", "")

        if not status_url:
            raise RuntimeError(
                f"fal.ai did not return a status URL. Response: {json.dumps(job)[:300]}"
            )

        # Poll for completion (fal.ai uses IN_QUEUE → IN_PROGRESS → COMPLETED)
        await _poll_for_completion(
            client=client,
            url=status_url,
            headers=headers,
            poll_timeout=poll_timeout,
            status_field="status",
            completed_statuses=["COMPLETED"],
            failed_statuses=["FAILED", "ERROR"],
        )

        # Fetch result from response_url
        if response_url:
            result_resp = await client.get(response_url, headers=headers)
            result_resp.raise_for_status()
            result_data = result_resp.json()
        else:
            result_data = {}

        video_url = result_data.get("video", {}).get("url", "")
        if not video_url:
            raise RuntimeError(
                f"fal.ai did not return a video URL. Response keys: {list(result_data.keys())}"
            )

        return {
            "url": video_url,
            "metadata": {
                "provider": "fal.ai",
                "model": active_model,
                "duration": duration_seconds,
            },
        }


def _aspect_ratio_to_size(aspect_ratio: str) -> str:
    """Convert aspect ratio string to Sora size parameter (WxH)."""
    mapping = {
        "9:16": "720x1280",
        "16:9": "1280x720",
        "1:1": "1080x1080",
    }
    return mapping.get(aspect_ratio, "1280x720")


async def _call_sora_video(
    api_key: str,
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "9:16",
    poll_timeout: int = 360,
) -> Dict[str, Any]:
    """Submit a video generation request to OpenAI Sora 2 and poll for result.

    Uses the OpenAI Videos API:
      POST  https://api.openai.com/v1/videos           → create job
      GET   https://api.openai.com/v1/videos/{id}       → poll status
      GET   https://api.openai.com/v1/videos/{id}/content → download MP4
    """
    submit_url = "https://api.openai.com/v1/videos"
    auth_headers = {
        "Authorization": f"Bearer {api_key}",
    }

    # Sora uses 'size' (WxH) not 'aspect_ratio', and 'seconds' not 'duration'
    size = _aspect_ratio_to_size(aspect_ratio)
    # Clamp duration to Sora's 5-20s range
    seconds = max(5, min(duration_seconds, 20))

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Create video generation job (multipart/form-data)
        resp = await client.post(
            submit_url,
            headers=auth_headers,
            data={
                "model": "sora-2",
                "prompt": prompt,
                "size": size,
                "seconds": str(seconds),
            },
        )
        resp.raise_for_status()
        job = resp.json()

        video_id = job.get("id", "")
        if not video_id:
            raise RuntimeError(
                f"OpenAI Sora did not return a video ID. Response: {json.dumps(job)[:300]}"
            )

        logger.info("sora_job_created", video_id=video_id, status=job.get("status"))

        # 2. Poll for completion
        poll_url = f"https://api.openai.com/v1/videos/{video_id}"
        await _poll_for_completion(
            client=client,
            url=poll_url,
            headers=auth_headers,
            poll_timeout=poll_timeout,
            status_field="status",
            completed_statuses=["completed"],
            failed_statuses=["failed", "cancelled"],
        )

        # 3. Download the MP4 binary from the content endpoint
        content_url = f"https://api.openai.com/v1/videos/{video_id}/content"

        return {
            "url": content_url,
            "is_binary_download": True,
            "auth_headers": auth_headers,
            "metadata": {
                "provider": "OpenAI Sora",
                "model": "sora-2",
                "video_id": video_id,
                "duration": seconds,
                "size": size,
            },
        }


async def _download_video(
    url: str,
    output_dir: str,
    headers: Optional[Dict[str, str]] = None,
) -> Path:
    """Download a video from a URL to persist it locally.

    Args:
        url: Video URL (can be a public fal.ai URL or an authenticated OpenAI endpoint).
        output_dir: Directory to save the MP4 file.
        headers: Optional auth headers needed for the download (e.g. Sora content endpoint).
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid4()}.mp4"
    file_path = out_path / filename

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url, headers=headers or {})
        resp.raise_for_status()
        file_path.write_bytes(resp.content)

    logger.info("video_downloaded", path=str(file_path), size_bytes=file_path.stat().st_size)
    return file_path
