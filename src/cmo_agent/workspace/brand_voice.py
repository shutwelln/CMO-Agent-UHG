"""Brand voice file loading."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()

DEFAULT_BRAND_VOICES_DIR = Path("./data/brand_voices")


class BrandVoiceLoader:
    """Loads brand voice text files from disk."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or DEFAULT_BRAND_VOICES_DIR

    def load(self, filename: str) -> str:
        """Load a brand voice file by filename.

        Args:
            filename: Filename relative to base_dir (e.g. 'uhg.txt')

        Returns:
            The brand voice text content.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        path = self.base_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Brand voice file not found: {path}")
        content = path.read_text(encoding="utf-8")
        logger.debug("brand_voice_loaded", file=str(path), length=len(content))
        return content

    def exists(self, filename: str) -> bool:
        return (self.base_dir / filename).exists()


# ── Convenience function ─────────────────────────────────────────────────
_default_loader = BrandVoiceLoader()


def load_brand_voice(filename: str) -> str:
    """Load a brand voice file using the default loader."""
    return _default_loader.load(filename)
