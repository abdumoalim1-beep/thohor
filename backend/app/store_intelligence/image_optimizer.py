from __future__ import annotations

from io import BytesIO

import httpx
from PIL import Image, ImageOps

from app.crawler.security import validate_url

MAX_IMAGE_BYTES = 15 * 1024 * 1024


async def download_and_optimize_image(url: str, *, quality: int = 82, max_edge: int = 2000) -> tuple[bytes, bytes, int, int]:
    validate_url(url)
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        response = await client.get(url, headers={"Accept": "image/*"})
        response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if not content_type.startswith("image/"):
        raise ValueError("URL did not return an image")
    original = response.content
    if not original or len(original) > MAX_IMAGE_BYTES:
        raise ValueError("image is empty or exceeds the 15 MB limit")
    with Image.open(BytesIO(original)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        width, height = image.size
        output = BytesIO()
        image.save(output, format="WEBP", quality=max(50, min(95, quality)), method=6, optimize=True)
    return original, output.getvalue(), width, height
