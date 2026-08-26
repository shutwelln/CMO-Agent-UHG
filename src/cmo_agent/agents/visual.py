"""Visual Agent - image generation for marketing content."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import structlog

from ..db.database import Database
from ..db.repositories import DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality.visual_evaluator import PostGenerationEvaluator
from ..quality.visual_spec import (
    ImageSpec,
    VisualSpecRefiner,
    spec_to_prompt,
    validate_spec_coverage,
)
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# Max times to regenerate an image if post-gen evaluation fails
_MAX_VISUAL_REGENERATIONS = 2

# Supported image platforms — tiered by quality and use case
PLATFORM_SDXL = "sdxl"  # Low tier: bulk SEO filler, backgrounds, experiments
PLATFORM_DALLE = "dall-e-3"  # Medium tier: landing pages, DMA pages, merchant tiles
PLATFORM_GEMINI = "gemini"  # High tier: hero banners, homepage visuals, investor decks
PLATFORM_PLACEHOLDER = "placeholder"

# Tier labels for user-facing selection
IMAGE_TIERS = {
    "low": {
        "platform": PLATFORM_SDXL,
        "label": "Budget",
        "model_name": "Stable Diffusion XL",
        "cost_approx": "~$0.01-$0.03/image",
        "best_for": "Bulk SEO filler, background illustrations, experiments",
    },
    "medium": {
        "platform": PLATFORM_DALLE,
        "label": "Standard",
        "model_name": "DALL-E 3",
        "cost_approx": "~$0.04-$0.08/image",
        "best_for": "Landing pages, DMA pages, merchant tiles",
    },
    "high": {
        "platform": PLATFORM_GEMINI,
        "label": "Premium",
        "model_name": "Gemini 3 Pro",
        "cost_approx": "~$0.05-$0.10/image (estimate)",
        "best_for": "Hero banners, homepage visuals, investor decks",
    },
}


class VisualAgent(BaseAgent):
    """Generates marketing images using a tiered model system.

    Three tiers:
    - Low (SDXL via FAL.ai): fast, cheap bulk generation
    - Medium (DALL-E 3): quality-per-dollar workhorse
    - High (Gemini 3 Pro): premium hero content

    Produces social media graphics, newsletter header images,
    infographics, and branded visual content.
    """

    agent_id = "visual_agent"
    agent_name = "Visual Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        openai_api_key: str = "",
        gemini_api_key: str = "",
        gemini_image_model: str = "gemini-3-pro-image-preview",
        fal_api_key: str = "",
        sdxl_model: str = "fal-ai/fast-sdxl",
        media_storage: Optional[Any] = None,
        proofreader: Optional[Any] = None,
        text_overlay: Optional[Any] = None,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._workspace_mgr = workspace_manager
        self._openai_api_key = openai_api_key
        self._gemini_api_key = gemini_api_key
        self._gemini_image_model = gemini_image_model
        self._fal_api_key = fal_api_key
        self._sdxl_model = sdxl_model
        self._media_storage = media_storage
        self._proofreader = proofreader
        self._text_overlay = text_overlay
        self._scanning_llm = scanning_llm
        self._spec_refiner = VisualSpecRefiner(generation_llm=llm, critique_llm=scanning_llm)
        self._evaluator = PostGenerationEvaluator(llm=llm)
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        ws_label = workspace_id or "all workspaces"
        return f"""You are the Visual Agent for {ws_label}.
You generate marketing images — photography, illustrations, and abstract visuals.

You have THREE image generation tiers:
- Budget (SDXL): ~$0.01-$0.03/image — bulk SEO filler, background illustrations, experiments
- Standard (DALL-E 3): ~$0.04-$0.08/image — landing pages, DMA pages, merchant tiles
- Premium (Gemini 3 Pro): ~$0.05-$0.10/image — hero banners, homepage visuals, investor decks

IMPORTANT: You generate TEXTLESS images only. All images contain NO text, labels, typography,
or written content. If text on an image is needed, the Composition Pipeline handles that separately.

When creating images:
- Follow brand guidelines (colors, tone, style)
- Optimize for the target platform dimensions
- Always describe the generated image in your response
- Default to the "medium" (DALL-E 3) tier unless the user specifies otherwise
- Generate exactly the number of images requested — no more, no less

Standard dimensions:
- Social media square: 1024x1024
- Social media landscape: 1792x1024
- Newsletter header: 1792x1024
- Blog hero: 1792x1024
- Instagram story: 1024x1792"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="generate_image",
            description=(
                "Generate an image using the tiered model system. "
                "Tiers: 'low' (SDXL ~$0.01-$0.03), 'medium' (DALL-E 3 ~$0.04-$0.08), "
                "'high' (Gemini 3 Pro ~$0.05-$0.10). Default tier is 'medium'. "
                "Provide a detailed prompt, tier, size, and quality level. Returns the image URL."
            ),
        )
        async def generate_image(
            prompt: str,
            workspace_id: Optional[str] = None,
            tier: str = "medium",
            size: str = "1024x1024",
            quality: str = "standard",
            style: str = "natural",
        ) -> Dict[str, Any]:
            tier = tier.lower()
            tier_info = IMAGE_TIERS.get(tier, IMAGE_TIERS["medium"])
            platform = tier_info["platform"]

            try:
                if platform == PLATFORM_SDXL:
                    # Low tier: SDXL via FAL.ai
                    if not self._fal_api_key:
                        return {
                            "error": "FAL API key not configured. Set FAL_API_KEY in .env.",
                            "prompt": prompt,
                            "tier": tier,
                            "status": "skipped",
                        }
                    result = await _call_sdxl(
                        api_key=self._fal_api_key,
                        model=self._sdxl_model,
                        prompt=prompt,
                        size=size,
                    )

                elif platform == PLATFORM_GEMINI:
                    # High tier: Gemini 3 Pro
                    if not self._gemini_api_key:
                        return {
                            "error": "Gemini API key not configured. Set GEMINI_API_KEY in .env.",
                            "prompt": prompt,
                            "tier": tier,
                            "status": "skipped",
                        }
                    result = await _call_gemini(
                        api_key=self._gemini_api_key,
                        model=self._gemini_image_model,
                        prompt=prompt,
                        size=size,
                    )

                else:
                    # Medium tier (default): DALL-E 3
                    if not self._openai_api_key:
                        return {
                            "error": "OpenAI API key not configured. Set OPENAI_API_KEY in .env.",
                            "prompt": prompt,
                            "tier": tier,
                            "status": "skipped",
                        }
                    result = await _call_dalle(
                        api_key=self._openai_api_key,
                        prompt=prompt,
                        size=size,
                        quality=quality,
                        style=style,
                    )

                cdn_url = result["url"]
                asset_id = None
                if self._media_storage and workspace_id:
                    try:
                        media_metadata = {
                            "size": size,
                            "quality": quality,
                            "style": style,
                            "tier": tier,
                            "model": tier_info["model_name"],
                        }
                        if result["url"].startswith("file://"):
                            # Local file (e.g. Gemini base64 decode) — upload from disk
                            local_path = result["url"].removeprefix("file://")
                            asset = await self._media_storage.upload_from_file(
                                file_path=local_path,
                                workspace_id=workspace_id,
                                media_type="image",
                                source_agent=self.agent_id,
                                prompt=prompt,
                                metadata=media_metadata,
                            )
                        else:
                            # Remote URL (DALL-E, SDXL) — download then upload
                            asset = await self._media_storage.upload_from_url(
                                url=result["url"],
                                workspace_id=workspace_id,
                                media_type="image",
                                extension=".png",
                                source_agent=self.agent_id,
                                prompt=prompt,
                                metadata=media_metadata,
                            )
                        cdn_url = asset.cdn_url or result["url"]
                        asset_id = asset.id
                    except Exception as e:
                        logger.warning("media_upload_failed_using_temp_url", error=str(e))

                return {
                    "image_url": cdn_url,
                    "revised_prompt": result.get("revised_prompt", prompt),
                    "size": size,
                    "tier": tier,
                    "model": tier_info["model_name"],
                    "status": "generated",
                    "asset_id": asset_id,
                }
            except Exception as e:
                logger.error("image_generation_failed", tier=tier, error=str(e))
                return {"error": str(e), "prompt": prompt, "tier": tier, "status": "failed"}

        @self.tool_registry.register(
            name="create_image_prompt",
            description=(
                "Use the LLM to create an optimized DALL-E prompt from a content "
                "description and brand voice. Returns the prompt text."
            ),
        )
        async def create_image_prompt(
            description: str,
            workspace_id: str,
            image_type: str = "social_media",
            platform: str = "general",
            tier: str = "medium",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            # Generate structured spec
            spec_dict = await self._spec_refiner.generate_spec(
                user_description=f"{description} (image type: {image_type}, platform: {platform})",
                brand_voice=brand_voice,
                spec_type="image",
            )

            if not spec_dict:
                # Fallback to legacy prompt generation
                style_hints = _get_style_hints(image_type, platform)
                gen_prompt = f"""Create a detailed image prompt for:
Description: {description}
Image type: {image_type}
Platform: {platform}

Brand context:
{brand_voice[:500] if brand_voice else "No brand voice specified."}

Style guidance:
{style_hints}

RULES: NO TEXT in the image. Describe the scene concretely.
Return ONLY the image prompt, nothing else."""
                response = await self.llm.complete(
                    messages=[Message(role="user", content=gen_prompt)],
                    temperature=0.5,
                )
                return {
                    "prompt": response.content.strip(),
                    "image_type": image_type,
                    "platform": platform,
                }

            # Refine spec
            spec_dict = await self._spec_refiner.refine_spec(
                spec=spec_dict,
                brand_voice=brand_voice,
            )

            # Convert spec to provider-specific prompt
            try:
                image_spec = ImageSpec(**spec_dict)
            except Exception:
                image_spec = ImageSpec()
                logger.warning("image_spec_validation_fallback")

            # Map tier to provider
            tier_to_provider = {"low": "sdxl", "medium": "dalle", "high": "gemini"}
            provider = tier_to_provider.get(tier, "dalle")
            prompt_text = spec_to_prompt(image_spec, provider)

            # Validate coverage
            coverage_warnings = validate_spec_coverage(image_spec, prompt_text)
            if coverage_warnings:
                logger.info("spec_coverage_warnings", warnings=coverage_warnings)

            return {
                "prompt": prompt_text,
                "image_type": image_type,
                "platform": platform,
                "spec": spec_dict,
            }

        @self.tool_registry.register(
            name="generate_social_graphic",
            description=(
                "Generate a social media graphic for a specific platform and topic. "
                "Combines prompt creation and image generation in one step."
            ),
        )
        async def generate_social_graphic(
            workspace_id: str,
            topic: str,
            platform: str = "instagram",
            overlay_text: Optional[str] = None,
        ) -> Dict[str, Any]:
            # Step 1: Create optimized prompt
            prompt_result = await create_image_prompt(
                description=topic,
                workspace_id=workspace_id,
                image_type="social_media",
                platform=platform,
            )

            dims = _platform_dimensions(platform)

            # Step 2: Generate image
            image_result = await generate_image(
                prompt=prompt_result["prompt"],
                workspace_id=workspace_id,
                size=dims,
                quality="hd",
                style="vivid",
            )

            # Step 3: Optional text overlay
            if overlay_text and image_result.get("status") == "generated" and self._text_overlay:
                overlay_result = await overlay_text_on_image(
                    image_url=image_result["image_url"],
                    text=overlay_text,
                    workspace_id=workspace_id,
                    position="bottom",
                    font_size=64,
                    stroke_width=3,
                    background_color="#000000",
                    background_opacity=160,
                )
                if overlay_result.get("status") == "generated":
                    image_result = overlay_result

            return {
                "topic": topic,
                "platform": platform,
                "prompt_used": prompt_result["prompt"],
                "image": image_result,
            }

        @self.tool_registry.register(
            name="generate_newsletter_image",
            description="Generate a header image for a newsletter draft.",
        )
        async def generate_newsletter_image(
            workspace_id: str,
            topic: str,
            draft_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            prompt_result = await create_image_prompt(
                description=topic,
                workspace_id=workspace_id,
                image_type="newsletter_header",
                platform="email",
            )

            image_result = await generate_image(
                prompt=prompt_result["prompt"],
                workspace_id=workspace_id,
                size="1792x1024",
                quality="hd",
                style="natural",
            )

            return {
                "topic": topic,
                "draft_id": draft_id,
                "prompt_used": prompt_result["prompt"],
                "image": image_result,
            }

        @self.tool_registry.register(
            name="suggest_visuals",
            description=(
                "Suggest image concepts for a piece of content. "
                "Returns a list of visual ideas with descriptions."
            ),
        )
        async def suggest_visuals(
            content: str,
            workspace_id: str,
            count: int = 3,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Suggest {count} image concepts for this marketing content.

CONTENT:
{content[:1000]}

BRAND CONTEXT:
{brand_voice[:300] if brand_voice else "No brand voice specified."}

For each suggestion provide:
1. A short title
2. A description of what the image should show
3. The recommended format (square, landscape, portrait)
4. The best platform for this image

Return as a JSON array of objects with keys: title, description, format, platform"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.8,
            )

            try:
                suggestions = json.loads(response.content)
            except (json.JSONDecodeError, TypeError):
                suggestions = [{"title": "Parse error", "description": response.content}]

            return {"suggestions": suggestions, "count": len(suggestions)}

        @self.tool_registry.register(
            name="overlay_text_on_image",
            description=(
                "Overlay crisp, proofread text onto an existing image using Pillow. "
                "Downloads the source image, renders text with configurable position, "
                "font size, colors, and optional background bar, then uploads the result. "
                "Text is automatically spell-checked before rendering."
            ),
        )
        async def overlay_text_on_image(
            image_url: str,
            text: str,
            workspace_id: Optional[str] = None,
            position: str = "center",
            font_size: int = 56,
            font_color: str = "#FFFFFF",
            stroke_color: str = "#000000",
            stroke_width: int = 3,
            background_color: Optional[str] = None,
            background_opacity: int = 160,
        ) -> Dict[str, Any]:
            if not self._text_overlay:
                return {
                    "error": "Text overlay not configured.",
                    "status": "skipped",
                }

            from ..text.overlay import TextOverlayConfig

            # Proofread text before rendering
            corrections = []
            rendered_text = text
            if self._proofreader:
                try:
                    pr = await self._proofreader.proofread(text, context="image text overlay")
                    if pr.has_corrections:
                        rendered_text = pr.corrected_text
                        corrections = pr.corrections
                        logger.info(
                            "visual_overlay_proofread_corrections",
                            count=len(pr.corrections),
                        )
                except Exception as e:
                    logger.warning("visual_overlay_proofread_failed", error=str(e))

            try:
                # Download source image
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(image_url)
                    resp.raise_for_status()
                    image_bytes = resp.content

                # Build overlay config
                config = TextOverlayConfig(
                    text=rendered_text,
                    position=position,
                    font_size=font_size,
                    font_color=font_color,
                    stroke_color=stroke_color,
                    stroke_width=stroke_width,
                    background_color=background_color,
                    background_opacity=background_opacity,
                )

                # Render overlay
                result_bytes = self._text_overlay.render(image_bytes, [config])

                # Upload to media storage if available
                cdn_url = image_url  # fallback to original
                asset_id = None
                if self._media_storage and workspace_id:
                    try:
                        asset = await self._media_storage.upload(
                            data=result_bytes,
                            workspace_id=workspace_id,
                            media_type="image",
                            extension=".png",
                            source_agent=self.agent_id,
                            prompt=f"Text overlay: {rendered_text[:100]}",
                        )
                        cdn_url = asset.cdn_url or image_url
                        asset_id = asset.id
                    except Exception as e:
                        logger.warning("overlay_media_upload_failed", error=str(e))

                return {
                    "image_url": cdn_url,
                    "text_rendered": rendered_text,
                    "corrections": corrections,
                    "status": "generated",
                    "asset_id": asset_id,
                }
            except Exception as e:
                logger.error("text_overlay_failed", error=str(e))
                return {"error": str(e), "text": text, "status": "failed"}


# ── Helper functions ──────────────────────────────────────────────────────


_DALLE_NO_TEXT_PREFIX = "Generate a purely visual image with no text, letters, or words. "


async def _call_dalle(
    api_key: str,
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "natural",
) -> Dict[str, Any]:
    """Call the OpenAI DALL-E 3 API to generate an image (medium tier)."""
    safe_prompt = _DALLE_NO_TEXT_PREFIX + prompt
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "dall-e-3",
                "prompt": safe_prompt,
                "n": 1,
                "size": size,
                "quality": quality,
                "style": style,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]


async def _call_sdxl(
    api_key: str,
    model: str,
    prompt: str,
    size: str = "1024x1024",
) -> Dict[str, Any]:
    """Call FAL.ai Stable Diffusion XL API to generate an image (low tier).

    Uses the same FAL API key already configured for video generation.
    """
    safe_prompt = _DALLE_NO_TEXT_PREFIX + prompt

    # Parse size into width/height
    try:
        w, h = size.split("x")
        width, height = int(w), int(h)
    except ValueError:
        width, height = 1024, 1024

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Submit generation request
        resp = await client.post(
            f"https://fal.run/{model}",
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "prompt": safe_prompt,
                "image_size": {"width": width, "height": height},
                "num_images": 1,
                "enable_safety_checker": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        image_data = data["images"][0]
        return {
            "url": image_data["url"],
            "revised_prompt": prompt,
        }


async def _call_gemini(
    api_key: str,
    model: str,
    prompt: str,
    size: str = "1024x1024",
    no_text_prefix: bool = True,
) -> Dict[str, Any]:
    """Call Google Gemini image generation API (high tier).

    Args:
        no_text_prefix: If True, prepend the "no text" safety prefix.
            Set to False for infographic/diagram prompts that NEED text.
    """
    import base64
    import os

    safe_prompt = (_DALLE_NO_TEXT_PREFIX + prompt) if no_text_prefix else prompt

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": api_key},
            json={
                "contents": [
                    {
                        "parts": [{"text": safe_prompt}],
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract image from response — Gemini returns base64-encoded
        # image data in the candidates[].content.parts[] array
        candidates = data.get("candidates", [])
        for candidate in candidates:
            parts = candidate.get("content", {}).get("parts", [])
            for part in parts:
                inline_data = part.get("inlineData")
                if inline_data and inline_data.get("mimeType", "").startswith("image/"):
                    # Decode base64 image and save to temp file, return path as URL
                    image_bytes = base64.b64decode(inline_data["data"])
                    temp_path = os.path.join("/tmp", f"gemini_{uuid4().hex[:12]}.png")
                    with open(temp_path, "wb") as f:
                        f.write(image_bytes)
                    return {
                        "url": f"file://{temp_path}",
                        "revised_prompt": prompt,
                    }

        raise ValueError(
            "Gemini API did not return an image. Check that the model supports image generation."
        )


def _platform_dimensions(platform: str) -> str:
    """Return DALL-E compatible dimensions for a platform."""
    dims = {
        "instagram": "1024x1024",
        "instagram_story": "1024x1792",
        "facebook": "1792x1024",
        "twitter": "1792x1024",
        "linkedin": "1792x1024",
        "newsletter": "1792x1024",
        "blog": "1792x1024",
        "pinterest": "1024x1792",
    }
    return dims.get(platform.lower(), "1024x1024")


def _get_style_hints(image_type: str, platform: str) -> str:
    """Return style guidance based on image type and platform."""
    hints = {
        "social_media": (
            "Bright, eye-catching, clean composition with a single strong focal point. "
            "Use shallow depth of field to separate subject from background. "
            "High contrast lighting. Leave negative space for optional text overlay. "
            "No clutter, no text, no signage."
        ),
        "newsletter_header": (
            "Professional, warm, inviting wide-format image. Soft directional lighting. "
            "Subtle gradient or bokeh background. Subject centered or rule-of-thirds. "
            "No text, no watermarks, no typography of any kind."
        ),
        "blog_hero": (
            "Editorial photography style. Clean composition with generous negative space "
            "on one side for text overlay. Muted or complementary color palette. "
            "No text, no signage, no labels in the scene."
        ),
        "infographic": (
            "Abstract data visualization aesthetic. Clean geometric shapes, smooth gradients, "
            "professional color palette. No text, numbers, or labels — those are added later."
        ),
        "quote_card": (
            "Minimal, serene background. Soft focus or gradient. Calming or inspiring mood. "
            "Maximum negative space for text overlay. Absolutely no text in the image."
        ),
    }
    return hints.get(
        image_type, "Professional marketing visual. Clean composition, no text or signage."
    )
