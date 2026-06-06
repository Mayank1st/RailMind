import uuid
from pathlib import Path

from fastapi import status
from supabase import create_client, Client
from app.config import settings
from app.utils.helpers import get_content_type
from app.core.exceptions import RailMindException

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE_MB = 5
MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def get_supabase_client() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def upload_pdf_to_supabase(pdf_bytes: bytes, file_name: str) -> str:
    client = get_supabase_client()

    storage_path = f"tickets/{file_name}"

    client.storage.from_(settings.SUPABASE_TICKET_BUCKET).upload(
        path=storage_path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )

    public_url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/public/"
        f"{settings.SUPABASE_TICKET_BUCKET}/{storage_path}"
    )

    return public_url


def upload_image_to_supabase(
    file_bytes: bytes,
    file_name: str,
    folder: str = "image",
    unique: bool = True,
) -> str:
    # ── Size check ─────────────────────────────────────────────────────────
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_IMAGE_SIZE_MB:
        raise RailMindException(
            code="RM-UPL-001",
            message=f"File size {size_mb:.2f}MB exceeds {MAX_IMAGE_SIZE_MB}MB limit",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    # ── Content-type detection from actual bytes ───────────────────────────
    content_type = get_content_type(file_bytes=file_bytes)
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise RailMindException(
            code="RM-UPL-002",
            message=f"Invalid file type: {content_type}. Allowed: JPEG, PNG, WebP",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    # ── Build storage path ─────────────────────────────────────────────────
    extension = MIME_TO_EXTENSION.get(content_type, ".bin")
    base_name = Path(file_name).stem  # strip any extension passed in

    if unique:
        final_name = f"{uuid.uuid4()}{extension}"
    else:
        final_name = f"{base_name}{extension}"

    storage_path = f"{folder}/{final_name}"

    # ── Upload (upsert=true overwrites if path exists) ─────────────────────
    client = get_supabase_client()
    try:
        client.storage.from_(settings.SUPABASE_IMAGE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={
                "content-type": content_type,
                "upsert": "true",
            },
        )
    except Exception as e:
        raise RailMindException(
            code="RM-UPL-003",
            message=f"Supabase upload failed: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from e

    return client.storage.from_(settings.SUPABASE_IMAGE_BUCKET).get_public_url(
        storage_path
    )
