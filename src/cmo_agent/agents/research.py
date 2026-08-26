"""Research Agent - RSS feeds, fraud monitoring, and opportunity scoring."""

from __future__ import annotations

import json
import re as _re
from datetime import datetime, timezone
from html.parser import HTMLParser as _HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx
import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, OpportunityRepo, ScanLogRepo, SourceRepo
from ..llm.base import BaseLLM
from .base import BaseAgent

logger = structlog.get_logger()


class ResearchAgent(BaseAgent):
    """Scans RSS feeds, fraud sources, and scores marketing opportunities."""

    agent_id = "research_agent"
    agent_name = "Research Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        max_iterations: int = 10,
        media_storage: Optional[Any] = None,
    ) -> None:
        self._opportunities = OpportunityRepo(db)
        self._sources = SourceRepo(db)
        self._config = ConfigRepo(db)
        self._scan_log = ScanLogRepo(db)
        self._media_storage = media_storage
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        ws_label = workspace_id or "all workspaces"
        return f"""You are the Research Agent for {ws_label}.
Your job is to scan external sources for marketing opportunities.

You can scan RSS feeds, Google Alerts, and fraud/scam sources.
For each item you find, score its relevance and actionability.

Scoring criteria:
- Relevance (0-10): How well does this match the workspace's keywords and audience?
- Recency (0-10): How fresh is the content?
- Engagement potential (0-10): Comments, shares, social signals
- Actionability (0-10): Can we create content from this?

Total score >= 25 is considered high-priority.
Always return structured results with source URLs, scores, and categorization."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="scan_rss_feeds",
            description="Scan all RSS feed sources for a workspace. Returns new opportunities found.",
        )
        async def scan_rss_feeds(workspace_id: str) -> Dict[str, Any]:
            sources = await self._sources.list_by_workspace(workspace_id, "rss")
            if not sources:
                return {"message": "No RSS feeds configured", "found": 0}

            keywords_raw = await self._config.get(workspace_id, "keywords")
            keywords = json.loads(keywords_raw) if keywords_raw else []

            log_id = await self._scan_log.create(self.agent_id, workspace_id, "rss")

            total_scanned = 0
            total_found = 0
            errors: List[str] = []
            results: List[Dict[str, Any]] = []

            for source in sources:
                try:
                    items = await _fetch_rss(source.url or "")
                    total_scanned += len(items)

                    for item in items:
                        guid = item.get("guid") or item.get("link", "")
                        if not guid:
                            continue
                        if await self._opportunities.exists_by_source_id("rss", guid):
                            continue

                        title = item.get("title", "")
                        desc = item.get("description", "")
                        combined = f"{title} {desc}".lower()

                        if not any(kw.lower() in combined for kw in keywords):
                            continue

                        score = _score_rss_item(item, keywords)
                        opp = await self._opportunities.create(
                            workspace_id=workspace_id,
                            source="rss",
                            source_url=item.get("link"),
                            source_id=guid,
                            title=title,
                            content=desc[:2000] if desc else None,
                            score=score,
                            score_breakdown={
                                "relevance": _kw_score(combined, keywords),
                                "recency": _pub_recency(item.get("pubDate")),
                                "engagement": 5,  # RSS doesn't have engagement metrics
                                "actionability": _rss_actionability(title, desc),
                            },
                            category="news_announcement",
                        )
                        total_found += 1
                        results.append(
                            {
                                "id": opp.id,
                                "title": title[:100],
                                "source": source.name,
                                "score": score,
                            }
                        )

                    await self._sources.update_last_checked(source.id)

                except Exception as e:
                    err = f"{source.name}: {e}"
                    logger.error("rss_scan_error", error=err)
                    errors.append(err)

            await self._scan_log.complete(log_id, total_scanned, total_found, errors or None)
            return {
                "workspace_id": workspace_id,
                "feeds_scanned": len(sources),
                "items_scanned": total_scanned,
                "opportunities_found": total_found,
                "errors": errors,
                "results": results[:20],
            }

        @self.tool_registry.register(
            name="scan_fraud_sources",
            description="Scan fraud/scam RSS feeds for a workspace. Returns fraud alerts.",
        )
        async def scan_fraud_sources(workspace_id: str) -> Dict[str, Any]:
            sources = await self._sources.list_by_workspace(workspace_id, "fraud_rss")
            if not sources:
                return {"message": "No fraud sources configured", "found": 0}

            log_id = await self._scan_log.create(self.agent_id, workspace_id, "fraud_rss")

            total_scanned = 0
            total_found = 0
            errors: List[str] = []
            results: List[Dict[str, Any]] = []

            for source in sources:
                try:
                    items = await _fetch_rss(source.url or "")
                    total_scanned += len(items)

                    for item in items:
                        guid = item.get("guid") or item.get("link", "")
                        if not guid:
                            continue
                        if await self._opportunities.exists_by_source_id("fraud", guid):
                            continue

                        title = item.get("title", "")
                        desc = item.get("description", "")

                        opp = await self._opportunities.create(
                            workspace_id=workspace_id,
                            source="fraud",
                            source_url=item.get("link"),
                            source_id=guid,
                            title=title,
                            content=desc[:2000] if desc else None,
                            score=30,  # Fraud alerts are always high priority
                            category="fraud_alert",
                        )
                        total_found += 1
                        results.append(
                            {
                                "id": opp.id,
                                "title": title[:100],
                                "source": source.name,
                            }
                        )

                    await self._sources.update_last_checked(source.id)

                except Exception as e:
                    err = f"{source.name}: {e}"
                    logger.error("fraud_scan_error", error=err)
                    errors.append(err)

            await self._scan_log.complete(log_id, total_scanned, total_found, errors or None)
            return {
                "workspace_id": workspace_id,
                "sources_scanned": len(sources),
                "items_scanned": total_scanned,
                "alerts_found": total_found,
                "errors": errors,
                "results": results[:20],
            }

        @self.tool_registry.register(
            name="score_opportunity",
            description="Use the LLM to score a content opportunity. Returns a score 0-40 with breakdown.",
        )
        async def score_opportunity(
            title: str, content: str, source: str, workspace_id: str
        ) -> Dict[str, Any]:
            keywords_raw = await self._config.get(workspace_id, "keywords")
            keywords = json.loads(keywords_raw) if keywords_raw else []

            from ..llm.base import Message

            prompt = f"""Score this content opportunity for marketing relevance.
Workspace keywords: {", ".join(keywords[:15])}

Title: {title}
Content: {content[:500]}
Source: {source}

Return a JSON object with these scores (0-10 each):
- relevance: How well does this match the keywords/audience?
- recency: Assume it's recent unless the content says otherwise.
- engagement: Estimated engagement potential.
- actionability: Can we create useful content from this?

Return ONLY valid JSON, no other text."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.3,
            )

            try:
                scores = json.loads(response.content)
                total = sum(
                    scores.get(k, 0)
                    for k in ["relevance", "recency", "engagement", "actionability"]
                )
                return {"scores": scores, "total": total}
            except (json.JSONDecodeError, TypeError):
                return {"scores": {}, "total": 0, "error": "Failed to parse LLM scores"}

        @self.tool_registry.register(
            name="get_workspace_keywords",
            description="Get the keyword list for a workspace.",
        )
        async def get_workspace_keywords(workspace_id: str) -> Dict[str, Any]:
            raw = await self._config.get(workspace_id, "keywords")
            keywords = json.loads(raw) if raw else []
            return {"workspace_id": workspace_id, "keywords": keywords}

        @self.tool_registry.register(
            name="read_spreadsheet",
            description=(
                "Read data from an XLSX or CSV file. Returns structured headers and rows. "
                "Use this to access spreadsheet data for analysis, context, or reference. "
                "Relative paths are resolved against the data/ directory."
            ),
        )
        async def read_spreadsheet(
            file_path: str,
            sheet_name: Optional[str] = None,
            max_rows: int = 500,
        ) -> Dict[str, Any]:
            from ..files.spreadsheet import read_spreadsheet as _read

            return _read(file_path, sheet_name=sheet_name, max_rows=max_rows)

        @self.tool_registry.register(
            name="list_data_files",
            description=(
                "List available spreadsheet and data files in the data directory. "
                "Use this to discover what files are available before reading them."
            ),
        )
        async def list_data_files(
            directory: Optional[str] = None,
        ) -> Dict[str, Any]:
            from ..files.spreadsheet import list_data_files as _list

            return _list(directory=directory)

        @self.tool_registry.register(
            name="fetch_webpage",
            description=(
                "Fetch a webpage and return its text content, page title, links, and images. "
                "Use this to research websites, find site structure, discover pages, "
                "or gather information from any public URL. Images include src URL, alt text, "
                "and dimensions when available (metadata only — images are not downloaded)."
            ),
        )
        async def fetch_webpage(url: str) -> Dict[str, Any]:
            try:
                async with httpx.AsyncClient(
                    timeout=20.0, follow_redirects=True, max_redirects=5
                ) as client:
                    resp = await client.get(
                        url,
                        headers={
                            "User-Agent": "CMOAgent/0.2.0",
                            "Accept": "text/html,application/xhtml+xml,*/*",
                        },
                    )
                    resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                return {"error": f"HTTP {e.response.status_code}", "url": url}
            except Exception as e:
                return {"error": str(e), "url": url}

            html = resp.text
            title, text, links, images = _extract_page_content(html, url)

            # Truncate text to keep within reasonable LLM context
            if len(text) > 8000:
                text = text[:8000] + "\n\n[Content truncated — 8000 char limit]"

            return {
                "url": url,
                "title": title,
                "text": text,
                "links": links[:50],
                "link_count": len(links),
                "images": images,
                "image_count": len(images),
            }

        @self.tool_registry.register(
            name="download_image",
            description=(
                "Download an image from a URL and store it in the media library. "
                "Use this after fetch_webpage to download a specific image (logo, hero image, "
                "product photo, etc.) discovered on a page. Returns the stored asset with "
                "CDN URL. Requires workspace_id."
            ),
        )
        async def download_image(
            image_url: str,
            workspace_id: str,
            description: str = "",
        ) -> Dict[str, Any]:
            if not self._media_storage:
                return {"error": "Media storage not configured", "url": image_url}

            # Guess extension from URL
            from pathlib import PurePosixPath

            path = PurePosixPath(image_url.split("?")[0])
            ext = path.suffix.lower() if path.suffix else ".png"
            if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"):
                ext = ".png"

            try:
                asset = await self._media_storage.upload_from_url(
                    url=image_url,
                    workspace_id=workspace_id,
                    media_type="image",
                    extension=ext,
                    source_agent=self.agent_id,
                    prompt=description or None,
                    metadata={"source_url": image_url},
                )
                return {
                    "asset_id": asset.id,
                    "cdn_url": asset.cdn_url,
                    "filename": asset.filename,
                    "source_url": image_url,
                    "workspace_id": workspace_id,
                }
            except Exception as e:
                return {"error": str(e), "url": image_url}

        @self.tool_registry.register(
            name="extract_brand_colors",
            description=(
                "Auto-extract brand colors from a website URL. Fetches the page, "
                "extracts color signals (meta theme-color, CSS custom properties, etc.), "
                "then uses the LLM to synthesize a brand palette. Stores the result in "
                "the workspace config so all agents receive the colors automatically."
            ),
        )
        async def extract_brand_colors(url: str, workspace_id: str) -> Dict[str, Any]:
            # Fetch the page
            try:
                async with httpx.AsyncClient(
                    timeout=20.0, follow_redirects=True, max_redirects=5
                ) as client:
                    resp = await client.get(
                        url,
                        headers={
                            "User-Agent": "CMOAgent/0.2.0",
                            "Accept": "text/html,application/xhtml+xml,*/*",
                        },
                    )
                    resp.raise_for_status()
            except Exception as e:
                return {"error": f"Failed to fetch {url}: {e}"}

            html = resp.text
            signals = _extract_color_signals(html)
            title, text, _, _ = _extract_page_content(html, url)

            # Count how many signals we found
            signal_count = sum(len(v) for v in signals.values())
            non_empty = {k: v for k, v in signals.items() if v}

            # Build LLM prompt
            from ..llm.base import Message

            prompt = f"""Analyze these color signals extracted from {url} and determine the brand's color palette.

Page title: {title}
Page text (first 500 chars): {text[:500]}

Color signals found:
{json.dumps(non_empty, indent=2) if non_empty else "No automated signals found — infer from the page content, brand name, and industry."}

Return a JSON object with EXACTLY these keys and hex color values:
- "primary": The main brand color (most prominent)
- "secondary": A supporting brand color
- "accent": An accent/highlight color
- "background": The primary background color (often white or near-white)
- "text": The primary text color (often dark gray or black)

Rules:
- All values must be 6-digit hex codes (e.g. "#1A2B3C")
- If you cannot determine a color with confidence, use sensible defaults that complement the primary
- The palette should look cohesive and professional
- Return ONLY the JSON object, no other text"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.2,
            )

            # Parse the LLM response
            try:
                # Handle markdown code fences
                content = response.content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1] if "\n" in content else content
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()
                palette = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                return {
                    "error": "Failed to parse LLM color response",
                    "raw": response.content[:300],
                }

            # Validate and normalize hex values
            required = ["primary", "secondary", "accent", "background", "text"]
            for key in required:
                if key not in palette:
                    return {"error": f"Missing required key: {key}"}
                expanded = _expand_hex(str(palette[key]))
                if not expanded:
                    return {"error": f"Invalid hex for {key}: {palette[key]}"}
                palette[key] = expanded

            # Store in config
            palette_json = json.dumps(palette)
            await self._config.set(workspace_id, "brand_colors", palette_json)

            confidence = "high" if signal_count >= 3 else "medium" if signal_count >= 1 else "low"

            return {
                "workspace_id": workspace_id,
                "palette": palette,
                "confidence": confidence,
                "signal_count": signal_count,
                "signals_found": non_empty,
                "stored": True,
                "message": f"Brand colors extracted and stored for {workspace_id}. All agents will now use these colors automatically.",
            }

        @self.tool_registry.register(
            name="set_brand_colors",
            description=(
                "Manually set brand colors for a workspace. Provide the primary color "
                "(required) and optionally secondary, accent, background, and text colors. "
                "Overwrites any previously auto-extracted colors."
            ),
        )
        async def set_brand_colors(
            workspace_id: str,
            primary: str,
            secondary: Optional[str] = None,
            accent: Optional[str] = None,
            background: Optional[str] = None,
            text: Optional[str] = None,
        ) -> Dict[str, Any]:
            # Validate and expand primary (required)
            p = _expand_hex(primary)
            if not p:
                return {"error": f"Invalid hex color for primary: {primary}"}

            palette: Dict[str, str] = {"primary": p}

            # Validate optional colors, use sensible defaults
            for key, val, default in [
                ("secondary", secondary, "#6B7280"),
                ("accent", accent, "#F59E0B"),
                ("background", background, "#FFFFFF"),
                ("text", text, "#1F2937"),
            ]:
                if val:
                    expanded = _expand_hex(val)
                    if not expanded:
                        return {"error": f"Invalid hex color for {key}: {val}"}
                    palette[key] = expanded
                else:
                    palette[key] = default

            palette_json = json.dumps(palette)
            await self._config.set(workspace_id, "brand_colors", palette_json)

            return {
                "workspace_id": workspace_id,
                "palette": palette,
                "stored": True,
                "message": f"Brand colors set for {workspace_id}. All agents will now use these colors automatically.",
            }


# ── Helper functions ──────────────────────────────────────────────────────


async def _fetch_rss(url: str) -> List[Dict[str, Any]]:
    """Fetch and parse an RSS feed, returning items as dicts."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers={"User-Agent": "CMOAgent/0.2.0"})
        resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)

    items: List[Dict[str, Any]] = []
    # Handle both RSS 2.0 (<item>) and Atom (<entry>)
    for item_el in root.iter("item"):
        items.append(_parse_rss_item(item_el))
    if not items:
        # Try Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry_el in root.iter("{http://www.w3.org/2005/Atom}entry"):
            items.append(_parse_atom_entry(entry_el, ns))

    return items


def _parse_rss_item(el: ElementTree.Element) -> Dict[str, Any]:
    return {
        "title": _text(el, "title"),
        "link": _text(el, "link"),
        "description": _text(el, "description"),
        "pubDate": _text(el, "pubDate"),
        "guid": _text(el, "guid") or _text(el, "link"),
    }


def _parse_atom_entry(el: ElementTree.Element, ns: Dict[str, str]) -> Dict[str, Any]:
    link_el = el.find("{http://www.w3.org/2005/Atom}link")
    link = link_el.get("href", "") if link_el is not None else ""
    return {
        "title": _atom_text(el, "title", ns),
        "link": link,
        "description": _atom_text(el, "summary", ns) or _atom_text(el, "content", ns),
        "pubDate": _atom_text(el, "updated", ns) or _atom_text(el, "published", ns),
        "guid": _atom_text(el, "id", ns) or link,
    }


def _text(parent: ElementTree.Element, tag: str) -> str:
    el = parent.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _atom_text(parent: ElementTree.Element, tag: str, ns: Dict[str, str]) -> str:
    el = parent.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    return (el.text or "").strip() if el is not None else ""


def _kw_score(text: str, keywords: List[str]) -> int:
    matches = sum(1 for kw in keywords if kw.lower() in text)
    if matches >= 4:
        return 10
    if matches >= 2:
        return 7
    if matches >= 1:
        return 4
    return 0


def _pub_recency(pub_date: Optional[str]) -> int:
    if not pub_date:
        return 5
    # Best effort parse; default to moderate score on failure
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(pub_date)
        age_hours = (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600
        if age_hours < 24:
            return 10
        if age_hours < 72:
            return 7
        if age_hours < 168:
            return 4
        return 2
    except Exception:
        return 5


def _rss_actionability(title: str, desc: str) -> int:
    text = f"{title} {desc}".lower()
    signals = ["guide", "how to", "tips", "list", "top", "best", "new", "update", "change"]
    hits = sum(1 for s in signals if s in text)
    if hits >= 3:
        return 9
    if hits >= 2:
        return 7
    if hits >= 1:
        return 5
    return 3


def _score_rss_item(item: Dict[str, Any], keywords: List[str]) -> int:
    title = item.get("title", "")
    desc = item.get("description", "")
    combined = f"{title} {desc}".lower()
    return (
        _kw_score(combined, keywords)
        + _pub_recency(item.get("pubDate"))
        + 5  # No engagement data for RSS
        + _rss_actionability(title, desc)
    )


# ── HTML extraction helpers ──────────────────────────────────────────────

_SKIP_IMAGE_PATTERNS = _re.compile(
    r"(spacer|pixel|tracking|blank|1x1|beacon|__utm|transparent)\.(gif|png|jpg|svg)$",
    _re.IGNORECASE,
)
_MAX_IMAGES = 20
_MIN_IMAGE_DIMENSION = 50


class _TextExtractor(_HTMLParser):
    """Simple HTML-to-text converter that also collects links."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}

    def __init__(self, base_url: str = "") -> None:
        super().__init__()
        self.text_parts: List[str] = []
        self.links: List[Dict[str, str]] = []
        self.images: List[Dict[str, Any]] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: List[str] = []
        self._base_url = base_url.rstrip("/")

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:  # type: ignore[type-arg]
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self.text_parts.append("\n")
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                if href.startswith("/"):
                    href = self._base_url + href
                link_text = ""  # filled in by handle_data
                self.links.append({"url": href, "text": link_text})
        if tag == "img" and self._skip_depth == 0 and len(self.images) < _MAX_IMAGES:
            attr_map = dict(attrs)
            src = attr_map.get("src", "")
            if not src or src.startswith("data:"):
                return
            if _SKIP_IMAGE_PATTERNS.search(src):
                return
            # Skip images with explicit tiny dimensions
            w = attr_map.get("width", "")
            h = attr_map.get("height", "")
            try:
                if w and int(w) < _MIN_IMAGE_DIMENSION:
                    return
                if h and int(h) < _MIN_IMAGE_DIMENSION:
                    return
            except ValueError:
                pass  # non-numeric dimensions (e.g. "100%"), keep the image
            resolved = urljoin(self._base_url + "/", src)
            img: Dict[str, Any] = {"src": resolved, "alt": attr_map.get("alt", "")}
            if w:
                img["width"] = w
            if h:
                img["height"] = h
            self.images.append(img)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title":
            self._in_title = False
            self.title = " ".join(self._title_parts).strip()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            self._title_parts.append(data)
        cleaned = data.strip()
        if cleaned:
            self.text_parts.append(cleaned)
            # Attach text to last link if we're inside one
            if self.links and not self.links[-1]["text"]:
                self.links[-1]["text"] = cleaned[:120]


def _extract_page_content(html: str, base_url: str = "") -> tuple:
    """Extract title, text content, links, and images from HTML."""
    parser = _TextExtractor(base_url)
    try:
        parser.feed(html)
    except Exception:
        pass
    text = "\n".join(parser.text_parts)
    # Collapse excessive whitespace
    text = _re.sub(r"\n{3,}", "\n\n", text).strip()
    # Deduplicate links
    seen: set = set()
    unique_links: List[Dict[str, str]] = []
    for link in parser.links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique_links.append(link)
    # Deduplicate images
    seen_imgs: set = set()
    unique_images: List[Dict[str, Any]] = []
    for img in parser.images:
        if img["src"] not in seen_imgs:
            seen_imgs.add(img["src"])
            unique_images.append(img)
    return parser.title, text, unique_links, unique_images


# ── Brand color extraction helpers ───────────────────────────────────────

# Patterns for meta tags (handles both attribute orderings)
_META_THEME_COLOR = _re.compile(
    r'<meta[^>]*(?:name=["\']theme-color["\'][^>]*content=["\']([^"\']+)["\']'
    r'|content=["\']([^"\']+)["\'][^>]*name=["\']theme-color["\'])',
    _re.IGNORECASE,
)
_META_TILE_COLOR = _re.compile(
    r'<meta[^>]*(?:name=["\']msapplication-TileColor["\'][^>]*content=["\']([^"\']+)["\']'
    r'|content=["\']([^"\']+)["\'][^>]*name=["\']msapplication-TileColor["\'])',
    _re.IGNORECASE,
)
_OG_IMAGE = _re.compile(
    r'<meta[^>]*(?:property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']'
    r'|content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\'])',
    _re.IGNORECASE,
)
_APPLE_TOUCH_ICON = _re.compile(
    r'<link[^>]*rel=["\']apple-touch-icon["\'][^>]*href=["\']([^"\']+)["\']',
    _re.IGNORECASE,
)
# CSS custom properties that look like brand colors
_CSS_COLOR_VARS = _re.compile(
    r"--(primary|secondary|accent|brand|main|base|theme|highlight)"
    r"[\w-]*color[\w-]*\s*:\s*(#[0-9a-fA-F]{3,8}|rgb[a]?\([^)]+\))",
    _re.IGNORECASE,
)
# Hex color validator
_HEX_COLOR = _re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _extract_color_signals(html: str) -> Dict[str, List[str]]:
    """Extract brand color signals from raw HTML.

    Scans meta tags and CSS custom properties for color values.
    Returns dict keyed by signal type with lists of discovered values.
    """
    signals: Dict[str, List[str]] = {
        "theme_color": [],
        "tile_color": [],
        "css_vars": [],
        "og_image": [],
        "apple_icon": [],
    }

    # Theme color meta tag
    for m in _META_THEME_COLOR.finditer(html):
        val = m.group(1) or m.group(2)
        if val and val not in signals["theme_color"]:
            signals["theme_color"].append(val)

    # MS tile color
    for m in _META_TILE_COLOR.finditer(html):
        val = m.group(1) or m.group(2)
        if val and val not in signals["tile_color"]:
            signals["tile_color"].append(val)

    # CSS custom properties
    for m in _CSS_COLOR_VARS.finditer(html):
        val = m.group(2)
        if val and val not in signals["css_vars"]:
            signals["css_vars"].append(val)

    # OG image (for logo color extraction context)
    for m in _OG_IMAGE.finditer(html):
        val = m.group(1) or m.group(2)
        if val and val not in signals["og_image"]:
            signals["og_image"].append(val)

    # Apple touch icon
    for m in _APPLE_TOUCH_ICON.finditer(html):
        val = m.group(1)
        if val and val not in signals["apple_icon"]:
            signals["apple_icon"].append(val)

    return signals


def _expand_hex(color: str) -> str:
    """Expand 3-digit hex to 6-digit and uppercase. Returns empty on invalid."""
    color = color.strip()
    if not color.startswith("#"):
        color = "#" + color
    if not _HEX_COLOR.match(color):
        return ""
    hex_part = color[1:]
    if len(hex_part) == 3:
        hex_part = "".join(c * 2 for c in hex_part)
    elif len(hex_part) == 8:
        hex_part = hex_part[:6]  # strip alpha
    return "#" + hex_part.upper()
