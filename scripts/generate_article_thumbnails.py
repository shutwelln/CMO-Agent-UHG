#!/usr/bin/env python3
"""Generate AI thumbnails for Saverwell Guide and Protection articles.

Queries Supabase for articles, generates 1200x630 editorial photographs
via DALL-E 3, Imagen 4, or Gemini 2.5 Flash, converts to WebP, uploads
to Supabase CDN, and updates article rows.

Usage:
    python scripts/generate_article_thumbnails.py                          # full run (missing thumbnails)
    python scripts/generate_article_thumbnails.py --dry-run                # generate, skip upload
    python scripts/generate_article_thumbnails.py --table guide            # only guide articles
    python scripts/generate_article_thumbnails.py --table protect          # only protection articles
    python scripts/generate_article_thumbnails.py --categories             # generate category hero images
    python scripts/generate_article_thumbnails.py --slug medicare-explained # single article
    python scripts/generate_article_thumbnails.py --featured --force --provider imagen4  # regen featured
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# Load .env into os.environ (keys the script reads directly)
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from cmo_agent.config import Settings  # noqa: E402

logger = structlog.get_logger()

# ── Constants ────────────────────────────────────────────────────────────────

DALLE_MODEL = "dall-e-3"
DALLE_SIZE = "1792x1024"  # closest DALL-E 3 size to 1200x630 (16:9-ish)
DALLE_QUALITY_STANDARD = "standard"  # $0.04/image
DALLE_QUALITY_HD = "hd"  # $0.12/image — used for featured articles
DALLE_STYLE = "natural"
NO_TEXT_PREFIX = (
    "Generate a purely visual image with no text, letters, or words. "
    "IMPORTANT: Use natural, varied color palettes — warm earth tones, muted blues, "
    "natural wood and fabric colors. Do NOT default to teal, mint green, or emerald "
    "accents. Avoid any consistent green color theme across images. "
)

BACKUP_DIR = Path("/tmp/thumbnail_backup")

SUPABASE_BUCKET = "cmo-agent"
CDN_PATH_PREFIX = "saverwell/thumbnails"

INTER_IMAGE_PAUSE = 2.0  # seconds between DALL-E calls

# Target output: 1200x630 WebP
TARGET_WIDTH = 1200
TARGET_HEIGHT = 630

# ── Diverse prompt pools ─────────────────────────────────────────────────────
# Each article gets a deterministic but unique combination based on slug hash.

GUIDE_PEOPLE: list[str] = [
    # ── White men ──
    "A 62-year-old white man with a silver crew cut and reading glasses, wearing a navy quarter-zip pullover",
    "A 69-year-old white man with a bushy silver mustache, wearing a denim jacket over a henley",
    "A 78-year-old white man with deep laugh lines and a full white beard, wearing a worn leather vest over flannel",
    "A 64-year-old white man with thinning gray hair and kind eyes, wearing a chambray work shirt with rolled sleeves",
    "A 73-year-old white man with a bald head and round glasses, wearing a rust-colored wool sweater",
    "A 67-year-old white man with a silver ponytail, wearing a faded denim shirt and a bolo tie",
    "A 71-year-old white man with thick white eyebrows and ruddy cheeks, wearing a brown canvas barn jacket",
    "A 65-year-old white man with salt-and-pepper hair and a crooked smile, wearing a gray henley and reading glasses on his forehead",
    "A 76-year-old white man with wispy white hair and a hearing aid visible, wearing a plaid flannel shirt",
    # ── White women ──
    "A 74-year-old white woman with a silver bob and pearl stud earrings, wearing a heather gray turtleneck",
    "A 66-year-old white woman with wavy silver hair past her shoulders, wearing an oatmeal linen shirt",
    "A 64-year-old white woman with auburn-gray hair and freckles, wearing a cranberry cotton cardigan",
    "A 72-year-old white woman with a short white pixie cut, wearing a denim apron over a striped shirt",
    "A 68-year-old white woman with silver hair in a loose French braid, wearing a dusty rose fleece vest",
    "A 77-year-old white woman with thin white hair and bright blue eyes, wearing a lavender cotton blouse",
    "A 63-year-old white woman with red-gray curly hair and tortoiseshell glasses, wearing a navy peacoat",
    "A 70-year-old white woman with a messy silver bun and paint-stained fingers, wearing an oversized cream sweater",
    # ── Black men ──
    "A 63-year-old Black man with close-cropped gray hair and wire-rim glasses, wearing an olive button-down",
    "A 73-year-old Black man with a shaved head and reading glasses on a chain, wearing a tan linen shirt",
    "A 66-year-old Black man with a silver goatee, wearing a burnt orange corduroy shirt",
    "A 70-year-old Black man with gray dreadlocks pulled back, wearing a charcoal wool overcoat",
    "A 78-year-old Black man with white stubble and deep-set eyes, wearing a brown leather bomber jacket",
    # ── Black women ──
    "A 68-year-old Black woman with natural gray curls, wearing a warm mustard cardigan",
    "A 70-year-old Black woman with short silver natural hair and bold earrings, wearing a rust-colored blouse",
    "A 67-year-old Black woman with close-cropped silver hair and elegant cheekbones, wearing a cobalt blue blouse",
    "A 75-year-old Black woman with silver twists and tortoiseshell reading glasses, wearing a camel wrap coat",
    "A 62-year-old Black woman with shoulder-length gray locs, wearing a burnt sienna tunic",
    # ── Latino/Latina ──
    "A 65-year-old Latina woman with shoulder-length salt-and-pepper hair, wearing a soft blue denim shirt",
    "A 61-year-old Latino man with dark wavy hair graying at the temples, wearing a light blue oxford shirt",
    "A 74-year-old Latina woman with silver hair in a low ponytail, wearing a terracotta linen blouse",
    "A 68-year-old Latino man with a thick silver mustache and weathered skin, wearing a tan suede jacket",
    "A 71-year-old Latina woman with curly gray hair and warm brown eyes, wearing a cream cable-knit sweater",
    # ── Asian ──
    "A 71-year-old East Asian man with thin silver hair, wearing a brown corduroy jacket over a white shirt",
    "A 77-year-old Japanese man with round tortoiseshell glasses, wearing a slate blue cardigan",
    "A 75-year-old Korean woman with round glasses and a warm smile, wearing a camel turtleneck",
    "A 68-year-old Chinese woman with silver hair cut in a practical bob, wearing a quilted navy vest",
    "A 63-year-old Vietnamese man with gray hair and laugh lines, wearing a khaki field jacket",
    "A 76-year-old East Asian woman with silver hair in a low bun, wearing a burgundy silk blouse",
    # ── South Asian ──
    "A 67-year-old South Asian man with a full gray beard, wearing a maroon sweater vest over a white shirt",
    "A 72-year-old South Asian woman with silver-streaked hair in a loose braid, wearing a warm copper tunic",
    "A 64-year-old South Asian man with steel-gray hair and a trimmed beard, wearing an olive canvas vest",
    # ── Filipino ──
    "A 68-year-old Filipino woman with silver-streaked dark hair, wearing a plum wrap top",
    "A 73-year-old Filipino man with thinning silver hair and deep smile lines, wearing a cream guayabera shirt",
    # ── Middle Eastern ──
    "A 66-year-old Middle Eastern man with a salt-and-pepper beard, wearing a charcoal cashmere sweater",
    "A 70-year-old Middle Eastern woman with silver-threaded dark hair under a warm brown shawl",
    # ── Native American ──
    "A 72-year-old Native American woman with long silver braids, wearing a terracotta blouse",
    "A 69-year-old Native American man with long gray hair and turquoise ring, wearing a denim shirt",
    # ── Mixed race / other ──
    "A 69-year-old mixed-race woman with curly silver-streaked hair, wearing a burgundy cotton sweater",
    "A 72-year-old Italian man with thick white hair swept back, wearing a cream linen blazer",
    "A 65-year-old mixed-race man with gray temples and warm brown skin, wearing a faded brick-red polo",
    # ── Couples / pairs ──
    "A retired couple — a 71-year-old Black man in a tan jacket and a 69-year-old white woman in a cream scarf",
    "A 73-year-old white couple — she in a dusty blue sweater, he in a brown corduroy shirt",
    "A 67-year-old Latino man and his 70-year-old wife in a maroon cardigan",
    "A 65-year-old South Asian couple — he with a gray beard in a navy vest, she in a copper-colored shawl",
    "A 74-year-old interracial couple — a Korean woman in a tan blazer and a white man in a chambray shirt",
    "A 68-year-old Black couple — she with silver natural hair in a rust blouse, he in an olive henley",
    # ── Solo with distinct features ──
    "A 76-year-old white woman using a walker, silver hair pinned back, wearing a warm red fleece",
    "A 80-year-old Black man with a cane resting beside him, white beard, wearing a tweed flat cap and brown jacket",
    "A 63-year-old Latina woman with thick gray-streaked hair and bright lipstick, wearing an indigo denim jacket",
    "A 71-year-old white man with a sun-weathered face and deep tan lines, wearing a faded baseball cap and flannel",
    "A 67-year-old East Asian woman with silver-rimmed bifocals and a practical short haircut, wearing a navy fleece pullover",
    # ── Additional for collision avoidance ──
    "A 79-year-old white woman with wild curly white hair and paint on her hands, wearing a loose linen smock",
    "A 66-year-old Black man with a flat top fade going gray, wearing a brown leather jacket and a gold chain",
    "A 70-year-old Pacific Islander woman with long graying hair over one shoulder, wearing a warm brown poncho",
    "A 62-year-old white man with a shaved head and hoop earring, wearing a black turtleneck and reading glasses on a cord",
    "A 77-year-old Latina woman with silver hair pulled tight in a bun and large hoop earrings, wearing a red blouse",
    "A 68-year-old East Asian man with a salt-and-pepper crew cut and square glasses, wearing a tan safari vest",
    "A 75-year-old white woman with strawberry-blonde hair fading to silver, wearing a forest green quilted jacket",
    "A 64-year-old Black woman with long silver box braids, wearing a camel wool coat and amber earrings",
    "A 73-year-old Middle Eastern man with a white mustache and deep-set brown eyes, wearing a herringbone blazer",
    "A 69-year-old white man with a weathered face and deep crow's feet, wearing a worn Carhartt jacket and a ball cap",
    "A 71-year-old Vietnamese woman with thin silver hair and gold-rimmed glasses, wearing a burgundy fleece zip-up",
    "A 66-year-old Latino man with slicked-back silver hair, wearing a denim trucker jacket over a white tee",
    "A 78-year-old white couple — she with short silver curls in a red sweater, he bald with glasses in a tan vest",
    "A 63-year-old Black woman with short natural gray hair and colorful beaded necklace, wearing an olive cotton shirt",
    "A 74-year-old South Asian woman with silver hair parted in the middle, wearing a mustard yellow shawl",
    "A 67-year-old white man with thick silver sideburns and ruddy cheeks, wearing a worn brown cardigan with elbow patches",
    "A 72-year-old Filipino woman with glasses on a beaded chain, wearing a periwinkle cotton blouse",
    "A 65-year-old mixed-race woman with wild curly silver hair and bright eyes, wearing an oversized rust flannel",
    "A 76-year-old Korean man with a gentle smile and thin silver hair, wearing a stone-gray linen shirt",
    "A 69-year-old Native American woman with silver hair in two braids and turquoise jewelry, wearing a brown leather vest",
]

GUIDE_SETTINGS: list[str] = [
    # ── Indoor home ──
    "at a bright kitchen table with morning light streaming through a window",
    "in a cozy home office with warm lamp light and a bookshelf behind",
    "on a comfortable couch in a warm living room with afternoon window light",
    "at a dining room table with natural light from a side window",
    "in a den with warm wood paneling and a reading lamp",
    "in a cluttered but cozy garage workshop with tools on pegboard behind",
    "in a laundry room doorway, leaning against the frame",
    "in a warm kitchen stirring something on the stove",
    # ── Outdoor / porch ──
    "on a screened back porch with dappled natural light through trees",
    "at a patio table with soft morning light and a garden in the background",
    "on a front porch swing with morning fog in the yard beyond",
    "in a vegetable garden, kneeling by raised beds in morning light",
    "walking along a tree-lined neighborhood sidewalk in golden hour light",
    "standing at a mailbox at the end of a suburban driveway, overcast soft light",
    "sitting on a park bench under a large oak tree with dappled shade",
    "on a back deck overlooking a modest backyard with a bird feeder",
    # ── Community / social ──
    "in a public library reading area with tall windows and natural light",
    "at a small-town coffee shop counter with warm overhead pendant lights",
    "in a community center meeting room with folding chairs and fluorescent light softened by window light",
    "in a doctor's office waiting room, seated in a chair by the window",
    "in a pharmacy aisle with soft overhead lighting",
    "at a farmers market booth with morning light and produce in the background",
    "in a church fellowship hall with warm wood floors and natural light from high windows",
    # ── Car / errands ──
    "sitting in the driver's seat of a parked car with the window half down, natural daylight",
    "standing outside a grocery store entrance with soft overcast light",
]

GUIDE_ACTIVITIES: list[str] = [
    # ── Reading / paper (keep a few) ──
    "reading a printed document through reading glasses",
    "reviewing paperwork spread on the table",
    "flipping through a printed guide booklet",
    # ── Digital (varied) ──
    "looking at a laptop screen with a focused expression",
    "squinting at a phone screen held at arm's length",
    "showing something on a tablet to someone off-camera",
    # ── Active / domestic ──
    "pouring coffee from a French press, mid-conversation with someone off-frame",
    "watering a potted plant on a windowsill",
    "sorting through mail just brought inside",
    "putting on a jacket and reaching for car keys by the front door",
    "opening the refrigerator and peering inside thoughtfully",
    "folding laundry on a bed with an absent-minded expression",
    "reaching for a book on a high shelf",
    # ── Social / interpersonal ──
    "laughing mid-conversation with someone just out of frame",
    "listening intently to someone across the table, chin resting on hand",
    "gesturing while explaining something with an animated expression",
    "hugging a grandchild who is partially visible in the frame",
    "waving to a neighbor from the front porch",
    # ── Outdoor / physical ──
    "walking a small dog on a leash along a quiet street",
    "kneeling in a garden pulling weeds with dirty gardening gloves",
    "carrying a paper grocery bag toward a front door",
    "sitting on a bench feeding pigeons with a distant gaze",
    "stretching after a walk, hands on hips, catching their breath",
    # ── Contemplative ──
    "looking out a window with a cup of coffee in hand, thoughtful expression",
    "standing in a doorway with arms crossed and a slight smile",
    "sitting quietly with eyes closed and hands folded in their lap",
]

GUIDE_ACCENTS: list[str] = [
    "A warm amber ceramic mug nearby.",
    "A navy blue throw pillow on the chair.",
    "A terracotta pot with a small cactus nearby.",
    "A cream-colored knit throw draped over the chair arm.",
    "A wooden picture frame on the shelf behind.",
    "A copper desk lamp casting warm light.",
    "A worn leather-bound book on the table.",
    "A soft gray blanket folded on the armrest.",
    "A red ceramic bowl with reading glasses resting on top.",
    "A well-used yellow legal pad with handwritten notes.",
    "A pair of worn slippers under the chair.",
    "",  # no accent — keep it simple
    "",  # no accent
    "",  # no accent
]

# Protection: person descriptions only (scene comes from PROTECT_TOPIC_SCENE_MAP)
PROTECTION_PEOPLE: list[str] = [
    "A 70-year-old white woman with gray hair in a bun, wearing a rust cardigan",
    "A 74-year-old white man with thin silver hair and wire-rim glasses, wearing a flannel shirt",
    "A 65-year-old Latina woman with reading glasses pushed up on her head, wearing a coral sweater",
    "A 71-year-old East Asian man with reading glasses and a charcoal cardigan",
    "A 76-year-old Korean woman with a silver bob and wire-rim glasses, wearing a slate blue cardigan",
    "A 63-year-old Black man with close-cropped gray hair, wearing an olive henley",
    "A 68-year-old white woman with a silver French braid, wearing a brown fleece vest",
    "A 72-year-old South Asian man with a gray beard, wearing a navy windbreaker",
    "A 67-year-old Middle Eastern woman with silver-threaded dark hair in a loose braid, wearing a plum cardigan",
    "A 69-year-old white man with a silver beard, wearing a brown corduroy jacket",
    "A 66-year-old Black woman with silver twists, wearing a warm clay-colored blouse",
    "A 73-year-old Filipino woman with silver hair, wearing a maroon pullover",
    "A 64-year-old Black man with reading glasses and a warm expression, wearing a chambray shirt",
    "A 75-year-old white woman with a white pixie cut, wearing a dusty rose down vest",
    "A 70-year-old Latino man with a silver mustache, wearing a tan jacket",
    "A 68-year-old South Asian woman with a silver streak in dark hair, wearing a navy blouse",
    "A 72-year-old Black woman with short natural gray hair, wearing a cream blouse",
    "A 66-year-old Filipino man with silver-streaked hair, wearing a brown polo shirt",
    "A 77-year-old white man with a bald head and thick white eyebrows, wearing a red buffalo check shirt",
    "A 63-year-old Latina woman with thick gray-streaked hair, wearing a denim jacket",
    "A 70-year-old white couple — he in a brown plaid shirt, she in a cream sweater",
    "A retired Black couple — he in an olive henley, she in a burgundy cardigan",
    "A 73-year-old mixed-race couple — she in a navy blouse, he in a charcoal sweater",
    "A 68-year-old interracial couple — a South Asian man in a navy vest and a white woman in a rust blouse",
    "A 71-year-old white woman with a silver bob, wearing a quilted vest",
    "A 65-year-old Black man with gray temples, wearing a brown bomber jacket",
    "A 74-year-old East Asian woman with silver hair in a bun, wearing a beige trench coat",
    "A 69-year-old white man with a gray ponytail, wearing a faded canvas jacket",
    "A 72-year-old Native American woman with long silver braids, wearing a clay-colored shawl",
    "A 66-year-old mixed-race man with salt-and-pepper hair, wearing a navy henley",
    "A 78-year-old white woman with thin white hair, wearing a lavender fleece",
    "A 70-year-old Black man with white stubble, wearing a tan corduroy jacket",
]

# Protection: abstract/symbolic scenes (used ~35% of the time)
PROTECTION_ABSTRACT: list[str] = [
    "Close-up of weathered hands carefully feeding a document into a small home paper shredder on a desk. Warm lamp light. Natural skin — age spots, veins, real texture",
    "A home desk with a closed laptop, a small brass padlock resting on top, and a cup of coffee. Warm morning window light. Calm, secure mood",
    "Close-up of a hand placing a credit card into a desk drawer with a small lock. Warm afternoon light. Wooden desk surface with natural grain",
    "A kitchen counter with a smartphone face-down next to a handwritten notepad that reads 'call bank'. Morning light, clean countertop, domestic calm",
    "Close-up of hands (brown skin, simple rings) holding a sealed envelope over a paper shredder. Warm side lighting. Careful, deliberate mood",
    "A tidy entryway table with a key bowl, a sealed letter, and a deadbolt visible on the front door. Natural daylight. Calm, organized mood",
    "Close-up of a hand turning a deadbolt lock on a front door. Worn brass hardware, chipped paint on the door frame. Late afternoon light. Protective mood",
    "A nightstand with a phone face-down, a glass of water, and a small notepad with a phone number circled. Warm bedside lamp light. Vigilant calm",
    "Close-up of a pair of scissors cutting up an expired credit card on a kitchen counter. Morning window light. Domestic, decisive mood",
    "A kitchen junk drawer partially open showing batteries, tape, and a sealed envelope marked IMPORTANT. Overhead light. Lived-in, real",
    "A front door peephole view (fisheye distortion) showing a blurry figure on the porch. Warm interior light behind the camera. Cautious mood",
    "Close-up of a hand writing a phone number on a sticky note stuck to a refrigerator door. Warm kitchen light. Preparedness mood",
    "A stack of opened and unopened mail on a kitchen table with a pair of reading glasses on top. Morning side light. Quiet domestic scene",
    "Close-up of a finger pressing the power button on a home Wi-Fi router. Warm lamp light. Minimal, security-minded",
]

PROTECTION_SETTINGS: list[str] = [
    "Warm afternoon light from a nearby window. Background: a tidy living room with a bookshelf.",
    "Morning light through a kitchen window. Clean, domestic setting with warm wood tones.",
    "Soft natural light from a side window. Background: a cozy home office with curtains.",
    "Warm lamp light at a home desk. Background: blurred bookshelf and family photos.",
    "Bright morning light in a breakfast nook. Calm, quiet atmosphere.",
    "Afternoon window light in a den. Warm wood paneling and a reading chair.",
    "Overcast daylight filtering through a screen door. Front entryway with coat hooks and shoes.",
    "Soft diffused daylight in a living room. Neutral tones, comfortable furniture.",
    "Dim evening light in a bedroom. Warm bedside lamp. Quiet, private mood.",
    "Fluorescent and natural light mixed in a bank lobby. Institutional but familiar.",
    "Harsh midday sun on a front porch. Suburban neighborhood visible in background.",
    "Warm overhead light in a small-town post office. Simple counters, familiar setting.",
]

MATTE_SUFFIX = (
    " Shot on 35mm Kodak Portra 400 film. Matte finish, no glossy highlights,"
    " no studio lighting. Soft diffused natural light, no specular reflections on skin."
    " Natural skin texture — visible pores, real wrinkles, age spots, uneven skin tone."
    " Slight film grain, natural color cast. Imperfect framing, not perfectly centered."
    " No airbrushing, no smoothing, no HDR look, no hyper-saturated colors."
    " Muted, true-to-life color palette — nothing overly vivid or digitally enhanced."
    " No text, no words, no letters, no logos, no watermarks."
    " Professional editorial photography with a candid, lived-in documentary feel."
    " This should look like a real photograph taken by a photojournalist, not AI-generated."
)


def _slug_hash(slug: str, pool_size: int) -> int:
    """Deterministic index from slug so each article gets a unique combo."""
    import hashlib
    h = int(hashlib.md5(slug.encode()).hexdigest(), 16)
    return h % pool_size


# ── Collision-free person assignment ─────────────────────────────────────────
# Hash-modulo guarantees collisions when articles > pool_size * 0.5 (birthday
# problem). Instead, we sort all slugs by their hash and assign person indices
# sequentially — guaranteeing every article gets a distinct person as long as
# pool_size >= article_count.
_GUIDE_PERSON_MAP: dict[str, int] = {}
_PROTECT_PERSON_MAP: dict[str, int] = {}


def populate_person_assignments(
    guide_slugs: list[str], protect_slugs: list[str]
) -> None:
    """Pre-compute collision-free person index for every article slug."""
    import hashlib

    _GUIDE_PERSON_MAP.clear()
    _PROTECT_PERSON_MAP.clear()

    # Sort by hash for deterministic but well-distributed ordering
    g_sorted = sorted(guide_slugs, key=lambda s: hashlib.md5(s.encode()).hexdigest())
    for i, slug in enumerate(g_sorted):
        _GUIDE_PERSON_MAP[slug] = i % len(GUIDE_PEOPLE)

    p_sorted = sorted(protect_slugs, key=lambda s: hashlib.md5(s.encode()).hexdigest())
    for i, slug in enumerate(p_sorted):
        _PROTECT_PERSON_MAP[slug] = i % len(PROTECTION_PEOPLE)

    logger.info(
        "person_assignments_ready",
        guide_articles=len(guide_slugs),
        guide_people=len(GUIDE_PEOPLE),
        protect_articles=len(protect_slugs),
        protect_people=len(PROTECTION_PEOPLE),
        guide_collisions=max(0, len(guide_slugs) - len(GUIDE_PEOPLE)),
        protect_collisions=max(0, len(protect_slugs) - len(PROTECTION_PEOPLE)),
    )


# ── Topic-to-scene mapping ───────────────────────────────────────────────────
# Each entry: (regex_pattern, [list of contextually appropriate scenes]).
# First match wins. Scenes describe setting + activity together so the image
# makes sense for the article subject. Pattern is matched against slug + title.

import re as _re

TOPIC_SCENE_MAP: list[tuple[str, list[str]]] = [
    # ── Phone / telecom ──
    (r"phone|cell|telecom|flip.phone|mobile", [
        "at a cell phone store counter, comparing two phones side by side with a skeptical squint. Bright retail lighting mixed with storefront window light",
        "sitting on the couch holding a smartphone at arm's length, squinting at the screen through reading glasses. Warm afternoon window light",
        "at the kitchen table with a phone bill printout and a smartphone, comparing numbers with a pen in hand. Morning light from a window",
        "standing in the phone aisle of a big-box store, reading the back of a phone box. Fluorescent store lighting, other shoppers blurred behind",
    ]),
    # ── Medicare ──
    (r"medicare|medicaid", [
        "in a doctor's office waiting room, flipping through a Medicare enrollment brochure. Plastic chairs, a wall clock, fluorescent lighting softened by a window",
        "at the kitchen table with Medicare paperwork spread out, a pen in hand, and reading glasses on. Morning light from a window",
        "at a pharmacy counter, handing a Medicare card to the pharmacist while holding a prescription printout. Bright pharmacy lighting",
        "sitting across from an insurance agent at a small desk, reviewing a printed comparison chart. Office with a window and blinds",
        "on the phone in the kitchen, holding a Medicare letter and asking questions with a focused expression. Warm overhead light",
    ]),
    # ── Medical alert systems ──
    (r"medical.alert", [
        "standing in the kitchen wearing a medical alert pendant, reaching for a mug on a high shelf. Morning light, domestic setting",
        "sitting in a comfortable armchair with a medical alert watch visible on the wrist, reading a magazine. Warm lamp light, cozy living room",
        "at the kitchen table examining a medical alert device in one hand and a brochure in the other. Bright morning light from a window",
        "gardening in the backyard with a medical alert pendant visible around the neck, kneeling by raised beds. Soft morning light",
    ]),
    # ── Hearing aids ──
    (r"hearing.aid|hearing|otc.hearing", [
        "at an audiologist's office, sitting in a chair while a hearing specialist adjusts a small device near the ear. Clinical but warm lighting",
        "at the kitchen table examining a small hearing aid in the palm of a hand, with the open case beside it. Morning window light",
        "sitting on the edge of a bed, tilting a hearing aid toward the ear with a concentrated expression. Warm bedroom light through curtains",
        "at a pharmacy counter, comparing two boxes of OTC hearing aids side by side. Bright retail lighting",
    ]),
    # ── Vision / glasses / eyes ──
    (r"vision|glasses|eye|eyewear|optom", [
        "at an optometrist's office, trying on frames in front of a small mirror. Bright clinical lighting, glasses display behind",
        "sitting at the kitchen table squinting at a newspaper through thick reading glasses. Morning side light from a window",
        "at an eyewear store counter, comparing two pairs of glasses while looking at a price tag. Retail display lighting",
        "in a bright living room, cleaning reading glasses with a cloth and holding them up to the light to check",
    ]),
    # ── Dental ──
    (r"dental", [
        "in a dentist's office waiting room, filling out a form on a clipboard. Bright fluorescent lighting, neutral walls",
        "at the kitchen table reviewing a dental insurance brochure with reading glasses on. Morning light, domestic setting",
    ]),
    # ── Prescription / pharmacy ──
    (r"prescription|drug.cost|part.d|rx", [
        "at a pharmacy counter, holding a prescription bottle and reading the label. Bright pharmacy lighting, shelves behind",
        "at the kitchen table with prescription bottles lined up, comparing prices on a printout. Morning light from a window",
        "standing in a pharmacy aisle, comparing two over-the-counter medications side by side. Soft overhead lighting",
    ]),
    # ── Insurance (auto, home, life, warranty) ──
    (r"insurance|warranty|auto.home|home.warranty", [
        "at the dining room table with an insurance policy document, a calculator, and a cup of coffee. Afternoon window light",
        "on the front porch, pointing at something on the roof while holding a clipboard with notes. Overcast daylight",
        "at the kitchen counter on the phone, with an insurance renewal letter open in front. Morning light",
        "in the living room with a laptop open, comparing insurance quotes side by side. Warm lamp light",
    ]),
    # ── Social Security ──
    (r"social.security|ssa|claim.*security|file.*62", [
        "at a government office counter, sliding paperwork to a clerk behind glass. Institutional fluorescent lighting, a take-a-number sign visible",
        "at the kitchen table with a Social Security statement printout, a calculator, and a pen. Morning window light",
        "on the phone in the living room, holding an official-looking letter with a concerned but focused expression. Afternoon light",
    ]),
    # ── Tax / deductions ──
    (r"tax|irs|deduction|irmaa", [
        "at a dining room table with tax forms, a calculator, and a pen, working through the paperwork. Warm overhead light and window light",
        "in a tax preparer's small office, sitting across the desk reviewing a return printout. Fluorescent and window light",
        "at the kitchen table with a laptop, a W-2 printout, and a mug of coffee, looking focused. Morning light",
    ]),
    # ── Retirement planning / savings / money ──
    (r"retire|pension|401k|roth|save|budget|spend|income|debt|payoff|invest|yield|money|financial|finance|cost|subscription.*audit|hidden.*drain|cut.*first|quit.*budget", [
        "at the kitchen table with a notebook, a calculator, and printed bank statements, doing the math. Morning light from a window",
        "in a home office, leaning back in a chair with a laptop open and a thoughtful expression. Warm afternoon light",
        "at the dining room table with bills sorted into piles, a pen in hand, and a cup of coffee. Soft morning light",
        "walking through a grocery store aisle, checking prices on items and comparing them. Soft overhead lighting",
        "at a bank counter, speaking with a teller while holding a printed statement. Bright bank lobby light",
    ]),
    # ── Caregiving / aging parents / nursing home ──
    (r"parent|caregiv|aging|family|spouse|loss|vulnerable|nursing.home|asset.protect", [
        "sitting on a couch next to an elderly parent, gently pointing at something on a tablet they share. Warm afternoon light",
        "at a kitchen table with an older parent, going through a folder of documents together. Morning light",
        "walking arm-in-arm with an elderly family member along a paved park path. Dappled afternoon sunlight",
        "standing in a doorway, having a gentle conversation with an older parent who is seated in a chair. Warm lamp light",
    ]),
    # ── Scam / fraud (guide-side articles) ──
    (r"scam|fraud|fake|impostor|exploit", [
        "on the phone in the kitchen, holding the phone slightly away from the ear with a skeptical, cautious expression. Warm afternoon light",
        "at the front door, peering through the peephole or chain lock at someone on the porch. Dim entryway, bright daylight outside",
        "at the kitchen table, examining a suspicious-looking letter closely with furrowed brows. Morning window light",
        "sitting in a living room armchair, showing a phone screen to someone off-camera with a concerned expression. Soft lamp light",
    ]),
    # ── AARP / discounts / deals ──
    (r"aarp|discount|deal|coupon|save.*grocery|restaurant", [
        "at a grocery store checkout, handing a loyalty card to the cashier with a slight smile. Bright store lighting",
        "at a restaurant table, looking at a menu with reading glasses while a server stands nearby. Warm ambient lighting",
        "at a ticket counter or box office, asking about senior pricing. Indoor lighting, counter visible",
    ]),
    # ── Government / benefits ──
    (r"government|benefits|ssi|wep", [
        "at a government services office, sitting in a waiting area holding a numbered ticket and paperwork. Fluorescent lighting, institutional setting",
        "at the kitchen table on the phone with an official letter in hand, taking notes on a notepad. Morning light",
    ]),
    # ── Home / vehicle / general cost ──
    (r"vehicle|car|home.warranty|home.insurance", [
        "standing next to a car in a driveway, looking at a mechanic's estimate printout. Overcast daylight",
        "on the front porch, talking to a contractor while holding a clipboard. Morning light",
    ]),
]

# ── Protection-specific topic scenes ─────────────────────────────────────────

PROTECT_TOPIC_SCENE_MAP: list[tuple[str, list[str]]] = [
    # ── Credit / identity / SSN ──
    (r"credit|identity|ssn|social.security.number|reading.*credit", [
        "at a bank counter, speaking with a teller while sliding a driver's license across the counter. Bright bank lobby with a line behind",
        "at a home desk, on the phone with one hand while the other hand covers personal information on a printed letter. Warm lamp light",
        "at a filing cabinet in a den, locking a drawer that contains important documents. Afternoon window light",
        "shredding a document at a home desk, feeding paper into a small personal shredder. Warm lamp light",
    ]),
    # ── Phone scams / impostor calls ──
    (r"bank.impostor|grandparent|phone.*scam|call|impostor", [
        "standing in the kitchen, holding a phone away from the ear and frowning with suspicion. Warm afternoon light from a window",
        "in the living room, pressing the end-call button on a phone with a relieved but annoyed expression. Soft lamp light",
        "at the kitchen counter, holding the phone to the ear with one hand and writing a number down with the other. Morning light",
    ]),
    # ── Online / website / phishing / email ──
    (r"online|website|phishing|email|data.breach|hacked|tech.support", [
        "at a kitchen table with a laptop open, leaning forward and squinting at the screen with a cautious expression. Morning window light",
        "at a home desk, pointing at something suspicious on a laptop screen with reading glasses on. Warm desk lamp light",
        "sitting at the kitchen table, typing on a laptop with a determined expression, changing passwords. Bright overhead light",
        "at the kitchen counter, frowning at a phone screen showing a suspicious text message. Morning light from behind",
    ]),
    # ── Password / account security / 2FA ──
    (r"password|account|two.factor|verification|2fa", [
        "at a kitchen table, writing in a small password notebook with a laptop open nearby. Morning light from a window",
        "at a home desk, holding a phone showing a verification code and typing on a laptop at the same time. Warm lamp light",
        "sitting at the kitchen table, carefully reading a printout titled 'account security' with reading glasses on. Afternoon light",
    ]),
    # ── Payment / wire / gift card / check ──
    (r"wire|payment|gift.card|check|peer|zelle|venmo|cashapp|charge|subscription", [
        "at a bank counter, speaking with a teller about a transaction while holding a printed bank statement. Bright bank lobby",
        "at the kitchen table, examining a bank statement printout line by line with a pen and highlighter. Morning light",
        "at a store checkout counter, examining a gift card skeptically before purchasing. Retail fluorescent lighting",
        "sitting on the couch, holding a phone open to a payment app and reading it carefully with a skeptical look. Afternoon light",
    ]),
    # ── Romance scams ──
    (r"romance", [
        "sitting alone at a kitchen table with a cup of tea, staring at a phone with a conflicted expression. Warm afternoon light, quiet mood",
        "at a home desk, reading something on a laptop with a worried, uncertain expression. Warm lamp light, evening",
    ]),
    # ── Smartphone security ──
    (r"smartphone|phone.security", [
        "sitting on the couch, holding a smartphone and carefully adjusting the settings with reading glasses on. Warm afternoon light",
        "at a kitchen table, holding a phone in one hand and pointing at the screen with the other, showing someone. Morning light",
    ]),
    # ── Tax identity theft ──
    (r"tax.*identity|tax.*theft", [
        "at a home desk with tax forms and a laptop, on the phone with the IRS with a focused expression. Warm lamp light, stacks of papers",
        "at the kitchen table, comparing a real IRS letter to a suspicious one, looking closely at the letterhead. Morning light",
    ]),
    # ── General scam / fraud fallback ──
    (r"scam|fraud|protect|suspect", [
        "at the kitchen table, examining a suspicious piece of mail with furrowed brows and reading glasses. Morning window light",
        "standing at the front door, looking through the chain lock at someone on the porch. Dim entryway, bright light outside",
        "in the living room on the phone, shaking their head no with a firm expression. Warm afternoon light",
        "at a kitchen counter, tearing up a piece of junk mail over a wastebasket. Morning light, decisive gesture",
    ]),
]


def _get_topic_scene(slug: str, title: str, scene_map: list[tuple[str, list[str]]]) -> str | None:
    """Match article to a contextually appropriate scene description."""
    text = f"{slug} {title}".lower()
    for pattern, scenes in scene_map:
        if _re.search(pattern, text):
            return scenes[_slug_hash(slug + "scene", len(scenes))]
    return None


def _build_diverse_guide_prompt(article: dict[str, Any]) -> str:
    """Build a unique editorial photograph prompt for a guide article."""
    slug = article["slug"]
    title = article["title"]

    # Use collision-free mapping if available, fallback to hash
    person_idx = _GUIDE_PERSON_MAP.get(slug)
    if person_idx is None:
        person_idx = _slug_hash(slug + "p", len(GUIDE_PEOPLE))
    person = GUIDE_PEOPLE[person_idx]

    # Topic-matched scene (setting + activity that makes sense for the article)
    scene = _get_topic_scene(slug, title, TOPIC_SCENE_MAP)
    if scene:
        prompt_body = f"{person}, {scene}."
    else:
        # Fallback for unmatched articles
        setting = GUIDE_SETTINGS[_slug_hash(slug + "s", len(GUIDE_SETTINGS))]
        activity = GUIDE_ACTIVITIES[_slug_hash(slug + "a", len(GUIDE_ACTIVITIES))]
        prompt_body = f"{person}, {setting}, {activity}."

    accent = GUIDE_ACCENTS[_slug_hash(slug + "c", len(GUIDE_ACCENTS))]
    parts = [
        f"Editorial photograph for an article titled \"{title}\".",
        prompt_body,
    ]
    if accent:
        parts.append(accent)
    parts.append(MATTE_SUFFIX)
    return " ".join(parts)


def _build_diverse_protection_prompt(article: dict[str, Any]) -> str:
    """Build a unique prompt for a protection article — scene matches the topic."""
    slug = article["slug"]
    title = article["title"]

    # Use collision-free mapping if available, fallback to hash
    person_idx = _PROTECT_PERSON_MAP.get(slug)
    if person_idx is None:
        person_idx = _slug_hash(slug + "pp", len(PROTECTION_PEOPLE))
    person = PROTECTION_PEOPLE[person_idx]

    # Topic-matched scene
    scene = _get_topic_scene(slug, title, PROTECT_TOPIC_SCENE_MAP)
    if scene:
        prompt_body = f"{person}. {scene}."
    else:
        # Fallback
        setting = PROTECTION_SETTINGS[_slug_hash(slug + "ps", len(PROTECTION_SETTINGS))]
        prompt_body = f"{person}. {setting}"

    parts = [
        f"Editorial photograph for an article titled \"{title}\".",
        prompt_body,
    ]
    parts.append(MATTE_SUFFIX)
    return " ".join(parts)

# ── Featured prompt templates (photorealistic, camera-specific) ──────────────

FEATURED_GUIDE_PROMPTS: dict[str, str] = {
    "medicare": (
        "Editorial photograph. A 72-year-old Black woman with silver locs pulled loosely "
        "back sits at a bright kitchen table, reading a printed document through "
        "tortoiseshell reading glasses. She wears a warm copper wrap blouse. Morning "
        "sunlight streams through a window to her left. A white ceramic coffee mug sits "
        "nearby. Background: soft-focus kitchen shelves with a wooden cutting board."
    ),
    "insurance": (
        "Editorial photograph. A mixed-race couple in their early 70s walk arm-in-arm "
        "along a quiet suburban sidewalk in autumn. The man wears a navy polo and khakis, "
        "the woman a cream cardigan and a warm scarf. Fallen leaves on the ground. Soft "
        "overcast afternoon light. Background: modest homes with front porches."
    ),
    "senior-products": (
        "Editorial photograph. A 75-year-old white woman with short white hair stands in "
        "her garden picking tomatoes from a raised bed. She wears a lavender fleece vest "
        "over a striped shirt. A subtle medical alert pendant visible around her neck. "
        "Soft morning light. Background: a weathered wooden fence and birdbath."
    ),
    "saving-money": (
        "Editorial photograph. A 66-year-old Latino man with salt-and-pepper hair stands "
        "at a kitchen counter clipping coupons from a newspaper with scissors. He wears a "
        "chambray button-down shirt with sleeves rolled. A mug of coffee and a fruit bowl "
        "nearby. Morning window light from behind. Background: a lived-in kitchen with "
        "magnets on the fridge."
    ),
    "retirement-taxes": (
        "Editorial photograph. An Asian couple in their late 60s sit side by side at a "
        "dining room table with a manila folder of tax documents, a desk calculator, "
        "and two mugs of tea. Both wear reading glasses. Warm overhead light and soft "
        "window light from the left. Background: dining room with a china cabinet."
    ),
    "caregiving": (
        "Editorial photograph. A 40-year-old woman walks arm-in-arm with her 78-year-old "
        "father along a paved park path. He uses a cane in his other hand. Dappled "
        "afternoon sunlight through trees. Both smiling. Background: a park bench and "
        "a pond in soft focus."
    ),
}

# Per-slug overrides for featured guide articles — used when multiple featured
# articles share the same category (e.g. two medicare articles both get the
# "medicare" category prompt, producing the same person). Checked first; falls
# back to category-based FEATURED_GUIDE_PROMPTS if no slug match.
FEATURED_GUIDE_SLUG_PROMPTS: dict[str, str] = {
    "save-money-medicare-premiums": (
        "Editorial photograph. A 69-year-old white man with a neat silver beard and "
        "wire-rim glasses stands in his garage workshop, leaning against a workbench "
        "covered in hand tools. He wears a faded navy pullover sweater. A bare bulb "
        "overhead and daylight through the open garage door. He holds a small calculator "
        "and a piece of paper, doing the math. Sawdust on the bench. Candid, hands-on."
    ),
    "cut-phone-bill-after-65": (
        "Editorial photograph. A 70-year-old South Asian man with thick silver hair "
        "stands at a cell phone store counter, holding two phones and comparing them side "
        "by side with a skeptical squint. He wears a burgundy henley and reading glasses "
        "pushed up on his forehead. Bright retail fluorescent lighting mixed with window "
        "light from the storefront. A sales associate blurred in the background."
    ),
    "save-on-hearing-aids": (
        "Editorial photograph. A 73-year-old Black woman with short natural gray hair "
        "and gold hoop earrings sits on the edge of her bed, tilting a small hearing aid "
        "toward her ear with a concentrated expression. She wears a coral blouse. Warm "
        "morning light through bedroom curtains. A nightstand with a glass of water and "
        "an alarm clock. Intimate, independent mood."
    ),
    "medicare-explained-simple-guide": (
        "Editorial photograph. A 74-year-old white woman with a silver bob sits in a "
        "doctor's office waiting room, flipping through a Medicare brochure. She wears "
        "a dusty blue cardigan over a white blouse. Harsh fluorescent ceiling light "
        "softened by a window to her left. Plastic chairs, a magazine rack, a wall clock. "
        "Focused but slightly overwhelmed expression. Real, institutional setting."
    ),
}

FEATURED_PROTECTION_PROMPTS: dict[str, str] = {
    "scams": (
        "Editorial photograph. A 70-year-old white woman with gray hair in a soft bun "
        "stands in her kitchen holding a cordless phone away from her ear, frowning. She "
        "wears a cozy rust-orange cardigan. A notepad on the counter has something "
        "scribbled on it. Warm afternoon light from a window behind her. Background: "
        "kitchen with a dish rack and a coffee maker. Authentic cautious expression."
    ),
    "identity": (
        "Editorial photograph. Close-up of an older man's weathered hands carefully "
        "feeding a document into a small home paper shredder on a cluttered desk. He "
        "wears a blue oxford shirt with rolled sleeves. Warm desk lamp light. A brown "
        "leather desk blotter underneath, scuffed and worn. Background: blurred den. "
        "Natural skin on hands — age spots, veins, real texture."
    ),
    "tech": (
        "Editorial photograph. A 65-year-old Black man with reading glasses perched on "
        "his nose leans forward in a kitchen chair, squinting at a laptop screen balanced "
        "on a placemat. He wears a charcoal henley. Morning light through a window over "
        "the sink. A coffee mug and a bowl of cereal nearby. Skeptical furrowed brow. "
        "Real, domestic, not a home office setup."
    ),
    "payments": (
        "Editorial photograph. A couple in their early 70s stand at a bank counter "
        "together, the woman pointing at a printout while the man speaks to a teller "
        "(partially visible). Fluorescent bank lighting mixed with window light from the "
        "entrance. She wears a tan jacket, he wears a plaid shirt. Concerned but calm."
    ),
    "fraud": (
        "Editorial photograph. A 68-year-old white woman with tortoiseshell reading "
        "glasses leans forward in a kitchen chair, studying a letter she holds under "
        "the overhead light. She wears a cream turtleneck. A crumpled envelope and "
        "her purse sit on the table. Background: a modest kitchen with a wall calendar "
        "and a refrigerator covered in magnets. Concentrated, slightly concerned."
    ),
}

# Per-slug prompts for featured protection articles — each describes a completely
# different person and scene to avoid the "same woman" problem caused by category_id
# mapping failures.
FEATURED_PROTECTION_SLUG_PROMPTS: dict[str, str] = {
    "bank-impostor-calls": (
        "Editorial photograph. A 70-year-old Latina woman with gray hair in a soft bun "
        "stands in her hallway near the front door, holding a cordless phone away from "
        "her ear and frowning. She wears a cozy rust-orange cardigan. A coat rack and "
        "a small entry table with keys visible. Afternoon light from a side window. "
        "Authentic cautious expression."
    ),
    "gift-card-scams": (
        "Editorial photograph. A 62-year-old Black man with close-cropped gray hair "
        "stands in a pharmacy checkout line, holding a gift card and squinting at the "
        "fine print on the back. He wears an olive henley. Fluorescent store lighting. "
        "Other customers blurred in background. Puzzled, skeptical expression."
    ),
    "password-safety-guide": (
        "Editorial photograph. A 68-year-old South Asian woman with a silver streak in "
        "her dark hair sits at her kitchen table with a laptop open, writing passwords "
        "in a small spiral notebook. She wears a navy blouse. Morning light from the "
        "kitchen window behind her. A mug of chai and a bowl of fruit on the table. "
        "Reading glasses resting on the table. Focused, careful expression."
    ),
    "phishing-scams-what-retirees-need-to-know": (
        "Editorial photograph. A 74-year-old white man with thin silver hair and "
        "wire-rim glasses stands at his kitchen counter, holding his phone at arm's "
        "length with a deeply skeptical squint. He wears a plaid flannel shirt. "
        "Morning light from a window over the sink. A coffee maker and a dish towel "
        "in the background. Suspicious, not buying it."
    ),
    "protecting-your-social-security-number": (
        "Editorial photograph. A 65-year-old Black woman with silver-streaked locs "
        "stands at a home filing cabinet, sliding a folder into a drawer. She wears "
        "a warm brown cardigan over a white blouse. Afternoon light from a nearby "
        "window. A small framed photo and a lamp on top of the cabinet. Calm, "
        "organized, deliberate mood. Shot from slightly below eye level."
    ),
    "tech-support-scams-what-you-need-to-know": (
        "Editorial photograph. A 71-year-old East Asian man with reading glasses "
        "pushed up on his forehead stands behind a kitchen chair, arms crossed, "
        "looking down at a laptop on the table with a guarded, unimpressed expression. "
        "He wears a charcoal henley. Warm overhead kitchen light and side window light. "
        "A half-eaten lunch plate pushed aside. Not falling for it."
    ),
}

# Default category mapping for protection articles (category_id → prompt key)
PROTECTION_CATEGORY_MAP: dict[str, str] = {
    "scams": "scams",
    "identity": "identity",
    "tech": "tech",
    "payments": "payments",
    "fraud": "fraud",
    # Fallback aliases
    "online-safety": "tech",
    "data-breach": "identity",
    "subscription": "payments",
}

# ── Category hero prompts ────────────────────────────────────────────────────

CATEGORY_HERO_PROMPTS: dict[str, str] = {
    "medicare": (
        "Warm editorial photograph of a senior reviewing paperwork with reading "
        "glasses at a bright kitchen table. Natural morning light. Warm wood tones "
        "and plants. Relaxed, informed expression. No text, no logos, no watermarks. "
        "Professional lifestyle photography. 1200x630 landscape."
    ),
    "insurance": (
        "Warm editorial photograph of a retired couple walking outdoors under a "
        "clear sky. Sense of security and confidence. Soft natural lighting, green "
        "park or garden path. No text, no logos, no watermarks. Professional "
        "lifestyle photography. 1200x630 landscape."
    ),
    "senior-products": (
        "Warm editorial photograph of a senior at home looking comfortable with "
        "a subtle medical alert wearable device visible. Cozy living room setting "
        "with natural light. Relaxed and safe. No text, no logos, no watermarks. "
        "Professional lifestyle photography. 1200x630 landscape."
    ),
    "saving-money": (
        "Warm editorial photograph of a couple planning finances at their kitchen "
        "table. Morning light, coffee cups, a few papers. Relaxed, confident "
        "expressions showing a sense of control. No text, no logos, no watermarks. "
        "Professional lifestyle photography. 1200x630 landscape."
    ),
    "retirement-taxes": (
        "Warm editorial photograph of a retired couple sitting together reviewing "
        "financial documents. Comfortable home office setting. Natural light, warm "
        "tones. Sense of accomplishment and preparation. No text, no logos, no "
        "watermarks. Professional lifestyle photography. 1200x630 landscape."
    ),
    "caregiving": (
        "Warm editorial photograph of an adult child helping their elderly parent "
        "at home. Natural light, warm colors, comfortable living room. Loving and "
        "supportive interaction. No text, no logos, no watermarks. Professional "
        "lifestyle photography. 1200x630 landscape."
    ),
}


# ── Image conversion ────────────────────────────────────────────────────────


def bytes_to_webp(raw_bytes: bytes) -> bytes:
    """Convert raw image bytes to 1200x630 WebP."""
    from PIL import Image

    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img = img.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85, method=4)
    return buf.getvalue()


async def download_and_convert_to_webp(url: str) -> bytes:
    """Download image from URL, resize to 1200x630, convert to WebP."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return bytes_to_webp(resp.content)


# ── Provider: DALL-E 3 ──────────────────────────────────────────────────────


async def generate_image_dalle(
    api_key: str, prompt: str, *, hd: bool = False
) -> dict[str, Any]:
    """Call DALL-E 3 and return {url, revised_prompt}."""
    safe_prompt = NO_TEXT_PREFIX + prompt
    quality = DALLE_QUALITY_HD if hd else DALLE_QUALITY_STANDARD
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": DALLE_MODEL,
                "prompt": safe_prompt,
                "n": 1,
                "size": DALLE_SIZE,
                "quality": quality,
                "style": DALLE_STYLE,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]


# ── Provider: Imagen 4 ──────────────────────────────────────────────────────


def generate_image_imagen4(api_key: str, prompt: str) -> bytes:
    """Generate via Google Imagen 4, return raw image bytes."""
    from google import genai

    client = genai.Client(api_key=api_key)
    safe_prompt = NO_TEXT_PREFIX + prompt
    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=safe_prompt,
        config=genai.types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="16:9",
            person_generation="allow_adult",
        ),
    )
    if not response.generated_images:
        raise RuntimeError("Imagen 4 returned no images")
    return response.generated_images[0].image.image_bytes


# ── Provider: Gemini 2.5 Flash ──────────────────────────────────────────────


def generate_image_gemini(api_key: str, prompt: str) -> bytes:
    """Generate via Gemini 2.5 Flash native image generation, return raw bytes."""
    from google import genai

    client = genai.Client(api_key=api_key)
    safe_prompt = NO_TEXT_PREFIX + prompt
    response = client.models.generate_content(
        model="gemini-3-pro-image-preview",
        contents=safe_prompt,
        config=genai.types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    raise RuntimeError("Gemini returned no image data")


# ── Supabase helpers ─────────────────────────────────────────────────────────


async def fetch_articles_without_thumbnails(
    settings: Settings, table: str
) -> list[dict[str, Any]]:
    """Fetch articles where thumbnail_url IS NULL."""
    if table == "guide_articles":
        select = "slug,title,subtitle,overview_md,category:guide_categories(slug)"
    else:
        select = "slug,title,subtitle,overview_md,category_id"
    url = (
        f"{settings.supabase_url}/rest/v1/{table}"
        f"?select={select}"
        "&thumbnail_url=is.null"
        "&order=slug"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_all_articles(
    settings: Settings, table: str, *, exclude_featured: bool = False
) -> list[dict[str, Any]]:
    """Fetch all articles, optionally excluding featured ones."""
    if table == "guide_articles":
        select = "slug,title,subtitle,overview_md,category:guide_categories(slug)"
    else:
        select = "slug,title,subtitle,overview_md,category_id"
    url = (
        f"{settings.supabase_url}/rest/v1/{table}"
        f"?select={select}"
        "&order=slug"
    )
    if exclude_featured:
        url += "&featured=neq.true"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_featured_articles(
    settings: Settings, table: str
) -> list[dict[str, Any]]:
    """Fetch articles where featured = true."""
    if table == "guide_articles":
        select = "slug,title,subtitle,overview_md,category:guide_categories(slug)"
    else:
        select = "slug,title,subtitle,overview_md,category_id"
    url = (
        f"{settings.supabase_url}/rest/v1/{table}"
        f"?select={select}"
        "&featured=eq.true"
        "&order=slug"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_single_article(
    settings: Settings, table: str, slug: str
) -> dict[str, Any] | None:
    """Fetch a single article by slug."""
    if table == "guide_articles":
        select = "slug,title,subtitle,overview_md,category:guide_categories(slug)"
    else:
        select = "slug,title,subtitle,overview_md,category_id"
    url = (
        f"{settings.supabase_url}/rest/v1/{table}"
        f"?select={select}"
        f"&slug=eq.{slug}"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None


async def upload_to_cdn(
    settings: Settings, data: bytes, storage_path: str
) -> str:
    """Upload bytes to Supabase Storage, return public CDN URL."""
    upload_url = (
        f"{settings.supabase_url}/storage/v1/object/{SUPABASE_BUCKET}/{storage_path}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            upload_url,
            content=data,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "image/webp",
                "x-upsert": "true",
            },
        )
        resp.raise_for_status()
    return (
        f"{settings.supabase_url}/storage/v1/object/public"
        f"/{SUPABASE_BUCKET}/{storage_path}"
    )


async def update_article_thumbnail(
    settings: Settings,
    table: str,
    slug: str,
    thumbnail_url: str,
    thumbnail_alt: str,
    thumbnail_prompt: str,
) -> bool:
    """PATCH the thumbnail fields on an article row."""
    url = f"{settings.supabase_url}/rest/v1/{table}?slug=eq.{slug}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={
                "thumbnail_url": thumbnail_url,
                "thumbnail_alt": thumbnail_alt,
                "thumbnail_prompt": thumbnail_prompt,
                "thumbnail_status": "pending",
            },
        )
        if resp.status_code in (200, 204):
            return True
        logger.error(
            "thumbnail_update_failed",
            slug=slug,
            status=resp.status_code,
            body=resp.text[:300],
        )
        return False


async def update_category_hero(
    settings: Settings,
    category_slug: str,
    hero_image_url: str,
    hero_image_alt: str,
    card_thumbnail_url: str | None = None,
) -> bool:
    """PATCH hero image fields on a guide_categories row."""
    url = (
        f"{settings.supabase_url}/rest/v1/guide_categories"
        f"?slug=eq.{category_slug}"
    )
    payload: dict[str, Any] = {
        "hero_image_url": hero_image_url,
        "hero_image_alt": hero_image_alt,
    }
    if card_thumbnail_url:
        payload["card_thumbnail_url"] = card_thumbnail_url
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=payload,
        )
        if resp.status_code in (200, 204):
            return True
        logger.error(
            "category_hero_update_failed",
            category=category_slug,
            status=resp.status_code,
            body=resp.text[:300],
        )
        return False


# ── Prompt builders ──────────────────────────────────────────────────────────


def build_prompt(
    article: dict[str, Any], table: str, *, featured: bool = False
) -> str:
    """Build the image generation prompt from article metadata."""
    title = article["title"]
    overview = article.get("overview_md", "")
    description = overview.split(".")[0] + "." if overview else ""

    if featured:
        prompt = _build_featured_prompt(article, table, description)
        if prompt:
            return prompt

    # Diverse prompts — unique person/setting/accent per article
    if table == "protection_articles":
        return _build_diverse_protection_prompt(article)
    return _build_diverse_guide_prompt(article)


def _build_featured_prompt(
    article: dict[str, Any], table: str, description: str
) -> str | None:
    """Select a photorealistic featured prompt based on article category/slug."""
    if table == "guide_articles":
        # Try per-slug prompt first (avoids duplicates when category has >1 featured)
        slug = article.get("slug", "")
        base = FEATURED_GUIDE_SLUG_PROMPTS.get(slug)
        if not base:
            cat_slug = _get_category_slug(article)
            base = FEATURED_GUIDE_PROMPTS.get(cat_slug)
        if not base:
            logger.warning("no_featured_prompt_for_category", slug=slug)
            return None
    else:
        # Protection articles — try per-slug prompt first (avoids category_id mismatch)
        slug = article.get("slug", "")
        base = FEATURED_PROTECTION_SLUG_PROMPTS.get(slug)
        if not base:
            # Fallback: map category_id to prompt key
            cat_id = str(article.get("category_id", ""))
            prompt_key = PROTECTION_CATEGORY_MAP.get(cat_id, "scams")
            base = FEATURED_PROTECTION_PROMPTS.get(prompt_key, "")
        if not base:
            return None

    # Append topic context from overview + no-text enforcement
    topic_hint = f" Topic context: {description}" if description else ""
    no_text = (
        " No text, no words, no letters, no logos, no watermarks, no overlays."
    )
    return base + topic_hint + no_text


def _get_category_slug(article: dict[str, Any]) -> str:
    """Extract category slug from nested join or fallback."""
    cat = article.get("category")
    if isinstance(cat, dict):
        return cat.get("slug", "")
    return ""


def build_alt_text(article: dict[str, Any], table: str) -> str:
    """Build descriptive alt text from article metadata."""
    title = article["title"]
    if table == "protection_articles":
        return f"Illustration for {title} — online safety and scam protection guide"
    category = _get_category_slug(article)
    return f"Photo illustration for {title} — Saverwell {category} guide"


# ── Main pipeline ────────────────────────────────────────────────────────────


async def backup_existing_image(
    settings: Settings, slug: str
) -> None:
    """Download current thumbnail to /tmp/thumbnail_backup/ before overwriting."""
    storage_path = f"{CDN_PATH_PREFIX}/{slug}.webp"
    cdn_url = (
        f"{settings.supabase_url}/storage/v1/object/public"
        f"/{SUPABASE_BUCKET}/{storage_path}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(cdn_url)
            if resp.status_code == 200:
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                (BACKUP_DIR / f"{slug}.webp").write_bytes(resp.content)
                logger.info("backup_saved", slug=slug, path=str(BACKUP_DIR / f"{slug}.webp"))
            else:
                logger.info("no_existing_image_to_backup", slug=slug)
    except Exception as e:
        logger.warning("backup_failed", slug=slug, error=str(e))


async def _generate_with_provider(
    settings: Settings,
    prompt: str,
    provider: str,
    *,
    featured: bool = False,
) -> bytes:
    """Generate an image using the specified provider and return WebP bytes."""
    google_key = os.environ.get("GEMINI_API_KEY", "")

    if provider == "imagen4":
        if not google_key:
            raise RuntimeError("GEMINI_API_KEY required for Imagen 4")
        raw = generate_image_imagen4(google_key, prompt)
        return bytes_to_webp(raw)
    elif provider == "gemini":
        if not google_key:
            raise RuntimeError("GEMINI_API_KEY required for Gemini")
        raw = generate_image_gemini(google_key, prompt)
        return bytes_to_webp(raw)
    else:  # dalle (default)
        result = await generate_image_dalle(
            settings.openai_api_key, prompt, hd=featured
        )
        return await download_and_convert_to_webp(result["url"])


async def process_article(
    settings: Settings,
    article: dict[str, Any],
    table: str,
    dry_run: bool = False,
    *,
    provider: str = "dalle",
    featured: bool = False,
    force: bool = False,
) -> bool:
    """Generate thumbnail for a single article. Returns True on success."""
    slug = article["slug"]
    prompt = build_prompt(article, table, featured=featured)
    alt_text = build_alt_text(article, table)

    logger.info(
        "generating_thumbnail",
        slug=slug,
        table=table,
        provider=provider,
        featured=featured,
    )

    # Backup existing image before overwrite
    if force and not dry_run:
        await backup_existing_image(settings, slug)

    try:
        webp_data = await _generate_with_provider(
            settings, prompt, provider, featured=featured
        )
        logger.info(
            "image_generated",
            slug=slug,
            provider=provider,
            size_kb=len(webp_data) // 1024,
        )
    except Exception as e:
        logger.error("generation_failed", slug=slug, provider=provider, error=str(e))
        return False

    if dry_run:
        logger.info("dry_run_skip_upload", slug=slug, prompt=prompt[:100])
        return True

    # Upload to CDN
    storage_path = f"{CDN_PATH_PREFIX}/{slug}.webp"
    try:
        cdn_url = await upload_to_cdn(settings, webp_data, storage_path)
        logger.info("cdn_uploaded", slug=slug, cdn_url=cdn_url)
    except Exception as e:
        logger.error("cdn_upload_failed", slug=slug, error=str(e))
        return False

    # Update article row
    ok = await update_article_thumbnail(
        settings, table, slug, cdn_url, alt_text, prompt
    )
    if ok:
        logger.info("thumbnail_saved", slug=slug)
    return ok


async def process_categories(
    settings: Settings, dry_run: bool = False
) -> int:
    """Generate hero images for all categories. Returns success count."""
    success = 0
    for category_slug, prompt in CATEGORY_HERO_PROMPTS.items():
        logger.info("generating_category_hero", category=category_slug)

        try:
            result = await generate_image_dalle(settings.openai_api_key, prompt)
            image_url = result["url"]
        except Exception as e:
            logger.error("category_dalle_failed", category=category_slug, error=str(e))
            continue

        if dry_run:
            logger.info("dry_run_skip_category", category=category_slug)
            success += 1
            await asyncio.sleep(INTER_IMAGE_PAUSE)
            continue

        try:
            webp_data = await download_and_convert_to_webp(image_url)
        except Exception as e:
            logger.error("category_webp_failed", category=category_slug, error=str(e))
            continue

        storage_path = f"{CDN_PATH_PREFIX}/categories/{category_slug}-hero.webp"
        try:
            cdn_url = await upload_to_cdn(settings, webp_data, storage_path)
        except Exception as e:
            logger.error("category_upload_failed", category=category_slug, error=str(e))
            continue

        alt_text = f"Hero image for {category_slug.replace('-', ' ').title()} guides"
        ok = await update_category_hero(
            settings, category_slug, cdn_url, alt_text, cdn_url
        )
        if ok:
            success += 1
            logger.info("category_hero_saved", category=category_slug)

        await asyncio.sleep(INTER_IMAGE_PAUSE)

    return success


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate AI thumbnails for Saverwell articles"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate images but skip upload and DB update",
    )
    parser.add_argument(
        "--table",
        choices=["guide", "protect", "both"],
        default="both",
        help="Which table to process (default: both)",
    )
    parser.add_argument(
        "--categories",
        action="store_true",
        help="Generate category hero images",
    )
    parser.add_argument(
        "--slug",
        type=str,
        default=None,
        help="Process a single article by slug",
    )
    parser.add_argument(
        "--provider",
        choices=["dalle", "imagen4", "gemini"],
        default="dalle",
        help="Image generation provider (default: dalle)",
    )
    parser.add_argument(
        "--featured",
        action="store_true",
        help="Process only featured articles (uses photorealistic prompts)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if thumbnail already exists (backs up old image first)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process ALL articles (excludes featured when used without --featured)",
    )
    parser.add_argument(
        "--slugs-file",
        type=str,
        default=None,
        help="Path to a text file with one slug per line to process (implies --force)",
    )
    args = parser.parse_args()

    settings = Settings()

    # Validate API keys based on provider
    if args.provider == "dalle" and not settings.openai_api_key:
        logger.error("OPENAI_API_KEY not set (required for DALL-E)")
        sys.exit(1)
    if args.provider in ("imagen4", "gemini") and not os.environ.get("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY not set (required for Imagen 4 / Gemini)")
        sys.exit(1)
    if not args.dry_run and (
        not settings.supabase_url or not settings.supabase_service_role_key
    ):
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required for upload")
        sys.exit(1)

    start = time.time()
    total_success = 0
    total_failed = 0

    # Category heroes (always use DALL-E for backward compat)
    if args.categories:
        count = await process_categories(settings, args.dry_run)
        logger.info("categories_done", success=count, total=len(CATEGORY_HERO_PROMPTS))
        total_success += count
        total_failed += len(CATEGORY_HERO_PROMPTS) - count

    # Article thumbnails
    tables: list[str] = []
    if args.table in ("guide", "both"):
        tables.append("guide_articles")
    if args.table in ("protect", "both"):
        tables.append("protection_articles")

    # Load slugs file if provided
    slugs_from_file: set[str] | None = None
    if args.slugs_file:
        slugs_path = Path(args.slugs_file)
        if not slugs_path.exists():
            logger.error("slugs_file_not_found", path=args.slugs_file)
            sys.exit(1)
        slugs_from_file = {
            line.strip() for line in slugs_path.read_text().splitlines() if line.strip()
        }
        logger.info("loaded_slugs_file", count=len(slugs_from_file), path=args.slugs_file)
        args.force = True  # --slugs-file implies --force

    # Pre-compute collision-free person assignments across ALL articles
    all_guide_slugs = [
        a["slug"] for a in await fetch_all_articles(settings, "guide_articles")
    ]
    all_protect_slugs = [
        a["slug"] for a in await fetch_all_articles(settings, "protection_articles")
    ]
    populate_person_assignments(all_guide_slugs, all_protect_slugs)

    for table in tables:
        if args.slug:
            article = await fetch_single_article(settings, table, args.slug)
            articles = [article] if article else []
            if not articles:
                logger.warning("slug_not_found", slug=args.slug, table=table)
                continue
        elif slugs_from_file is not None:
            all_articles = await fetch_all_articles(settings, table)
            articles = [a for a in all_articles if a["slug"] in slugs_from_file]
        elif args.all:
            articles = await fetch_all_articles(
                settings, table, exclude_featured=not args.featured
            )
        elif args.featured:
            articles = await fetch_featured_articles(settings, table)
        else:
            articles = await fetch_articles_without_thumbnails(settings, table)

        logger.info(
            "articles_to_process",
            table=table,
            count=len(articles),
            featured=args.featured,
            provider=args.provider,
        )

        for article in articles:
            ok = await process_article(
                settings,
                article,
                table,
                args.dry_run,
                provider=args.provider,
                featured=args.featured,
                force=args.force,
            )
            if ok:
                total_success += 1
            else:
                total_failed += 1
            await asyncio.sleep(INTER_IMAGE_PAUSE)

    elapsed = time.time() - start
    logger.info(
        "thumbnail_generation_complete",
        success=total_success,
        failed=total_failed,
        elapsed_s=round(elapsed, 1),
        dry_run=args.dry_run,
        provider=args.provider,
        featured=args.featured,
    )


# ── Importable API for weekly_content_factory ────────────────────────────────


async def generate_for_slugs(
    slugs: list[str],
    table: str = "guide_articles",
    provider: str = "gemini",
    settings: Settings | None = None,
) -> dict[str, bool]:
    """Generate thumbnails for specific slugs. Returns {slug: success_bool}.

    This is the importable entry point used by ``weekly_content_factory.py``.
    Fetches article metadata from Supabase, generates images, uploads to CDN,
    and updates article rows.

    Args:
        slugs: List of article slugs to process.
        table: Supabase table name.
        provider: Image generation provider (dalle, gemini, imagen4).
        settings: CMO Agent settings. Loaded from .env if None.
    """
    if settings is None:
        settings = Settings()

    results: dict[str, bool] = {}
    for slug in slugs:
        article = await fetch_single_article(settings, table, slug)
        if article is None:
            logger.warning("generate_for_slugs_not_found", slug=slug)
            results[slug] = False
            continue

        ok = await process_article(
            settings,
            article,
            table,
            dry_run=False,
            provider=provider,
        )
        results[slug] = ok

        if ok:
            logger.info("generate_for_slugs_ok", slug=slug, provider=provider)
        else:
            logger.warning("generate_for_slugs_failed", slug=slug, provider=provider)

        await asyncio.sleep(INTER_IMAGE_PAUSE)

    return results


if __name__ == "__main__":
    asyncio.run(main())
