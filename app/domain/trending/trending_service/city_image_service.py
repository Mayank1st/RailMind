import asyncio
import io
import logging
import re

import httpx

from PIL import Image

from app.ai.prompts.city_image_prompts import city_image_prompt
from app.config import settings
from app.domain.trending.constants.trending import (
    CITY_IMAGE_ASPECT_RATIO,
    CITY_IMAGE_HEIGHT,
    CITY_IMAGE_MAX_BYTES,
    CITY_IMAGE_OUTPUT_FORMAT,
    CITY_IMAGE_RESOLUTION,
    CITY_IMAGE_SUBFOLDER,
    CITY_IMAGE_WEBP_QUALITIES,
    CITY_IMAGE_WIDTH,
    ERROR_CODE_TRENDING,
)
from app.integrations.replicate_client import run_replicate_model
from app.integrations.replicate_models import MODEL2
from app.integrations.supabase_client import (
    file_public_url_if_exists,
    upload_public_file,
)

logger = logging.getLogger(__name__)

IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 60


class CityImageService:
    """Weekly carousel images for trending destination cities.

    Reuse-first: an image already stored in the SUPABASE_BUCKET under
    {SUPABASE_TRENDING_FOLDER}/{CITY_IMAGE_SUBFOLDER}/{CITY}.webp is reused via
    its public URL; only missing cities are generated (nano-banana-2 via
    Replicate), center-cropped to 2:1 (1200x600), compressed to WebP under
    200KB and uploaded. Every failure returns None — cards render without an
    image, the weekly job never blocks."""

    @staticmethod
    def storage_folder() -> str:
        return f"{settings.SUPABASE_TRENDING_FOLDER}/{CITY_IMAGE_SUBFOLDER}"

    @staticmethod
    def storage_file_name(city_name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", city_name.strip().upper()).strip("_")
        return f"{safe}.webp"

    async def get_city_images(self, city_names: list[str]) -> dict[str, str]:
        """{city name -> public URL} for every city we could resolve.
        All cities run concurrently — generation is network-bound (~12s each),
        so 6 new cities cost ~one generation's wall-clock, not six."""
        urls = await asyncio.gather(
            *(self.get_or_create_city_image(name) for name in city_names)
        )
        return {name: url for name, url in zip(city_names, urls) if url}

    async def get_or_create_city_image(self, city_name: str) -> str | None:
        file_name = self.storage_file_name(city_name)

        try:
            # to_thread: sync HTTP call — must not block the parallel batch
            existing = await asyncio.to_thread(
                file_public_url_if_exists,
                settings.SUPABASE_BUCKET,
                self.storage_folder(),
                file_name,
            )
        except Exception:
            logger.warning(
                "%s city image storage lookup failed for %s",
                ERROR_CODE_TRENDING,
                city_name,
            )
            existing = None

        if existing:
            logger.info("city image reused | city=%s url=%s", city_name, existing)
            return existing

        try:
            return await self._generate_and_upload(city_name, file_name)
        except Exception:
            logger.exception(
                "%s city image generation failed for %s",
                ERROR_CODE_TRENDING,
                city_name,
            )
            return None

    async def _generate_and_upload(self, city_name: str, file_name: str) -> str:
        image_url = await run_replicate_model(
            model=MODEL2,
            model_input={
                "prompt": city_image_prompt(city_name),
                "aspect_ratio": CITY_IMAGE_ASPECT_RATIO,
                "resolution": CITY_IMAGE_RESOLUTION,
                "output_format": CITY_IMAGE_OUTPUT_FORMAT,
            },
        )

        async with httpx.AsyncClient(
            timeout=IMAGE_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            response = await client.get(str(image_url))
            response.raise_for_status()
            raw_bytes = response.content

        # to_thread: CPU-bound Pillow work + sync upload — keep the loop free
        webp_bytes = await asyncio.to_thread(self._to_card_webp, raw_bytes)
        public_url = await asyncio.to_thread(
            upload_public_file,
            settings.SUPABASE_BUCKET,
            f"{self.storage_folder()}/{file_name}",
            webp_bytes,
            "image/webp",
        )
        logger.info(
            "city image generated | city=%s size=%sKB url=%s",
            city_name,
            len(webp_bytes) // 1024,
            public_url,
        )
        return public_url

    @staticmethod
    def _to_card_webp(image_bytes: bytes) -> bytes:
        """Center-crop to 2:1, resize to 1200x600, WebP under CITY_IMAGE_MAX_BYTES
        (quality stepped down until it fits; smallest attempt kept otherwise)."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = image.size
        target_ratio = CITY_IMAGE_WIDTH / CITY_IMAGE_HEIGHT

        if width / height > target_ratio:  # too wide — trim equal sides
            crop_width = int(height * target_ratio)
            left = (width - crop_width) // 2
            image = image.crop((left, 0, left + crop_width, height))
        elif width / height < target_ratio:  # too tall — trim top/bottom
            crop_height = int(width / target_ratio)
            top = (height - crop_height) // 2
            image = image.crop((0, top, width, top + crop_height))

        image = image.resize(
            (CITY_IMAGE_WIDTH, CITY_IMAGE_HEIGHT), Image.Resampling.LANCZOS
        )

        webp_bytes = b""
        for quality in CITY_IMAGE_WEBP_QUALITIES:
            buffer = io.BytesIO()
            image.save(buffer, format="WEBP", quality=quality, method=6)
            webp_bytes = buffer.getvalue()
            if len(webp_bytes) <= CITY_IMAGE_MAX_BYTES:
                break
        return webp_bytes


city_image_service = CityImageService()
