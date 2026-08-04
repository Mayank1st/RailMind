import uuid
from pathlib import Path

import httpx
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

    storage_path = f"{settings.SUPABASE_TICKET_FOLDER}/{file_name}"

    client.storage.from_(settings.SUPABASE_BUCKET).upload(
        path=storage_path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )

    public_url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/public/"
        f"{settings.SUPABASE_BUCKET}/{storage_path}"
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

    storage_path = f"{settings.SUPABASE_IMAGE_FOLDER}/{folder}/{final_name}"

    # ── Upload (upsert=true overwrites if path exists) ─────────────────────
    client = get_supabase_client()
    try:
        client.storage.from_(settings.SUPABASE_BUCKET).upload(
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

    return client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(storage_path)


def ensure_private_bucket(bucket: str) -> None:
    """Create `bucket` as PRIVATE if it doesn't exist yet. Idempotent — an
    already-exists error from Supabase is the success case."""
    client = get_supabase_client()
    try:
        client.storage.create_bucket(bucket, options={"public": False})
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            return
        raise RailMindException(
            code="RM-UPL-004",
            message=f"Could not ensure private bucket {bucket}: {e}",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from e


def upload_private_file(
    bucket: str, storage_path: str, file_bytes: bytes, content_type: str
) -> str:
    """Uploads to a PRIVATE bucket and returns the storage path — deliberately
    not a URL, since the object has no public URL. Pair with create_signed_url."""
    client = get_supabase_client()
    try:
        client.storage.from_(bucket).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    except Exception as e:
        raise RailMindException(
            code="RM-UPL-003",
            message=f"Supabase upload failed: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from e

    return storage_path


def create_signed_url(bucket: str, storage_path: str, expires_in: int) -> str:
    """Short-lived signed URL for an object in a private bucket."""
    client = get_supabase_client()
    try:
        response = client.storage.from_(bucket).create_signed_url(
            storage_path, expires_in
        )
    except Exception as e:
        raise RailMindException(
            code="RM-UPL-005",
            message=f"Could not sign {storage_path}: {e}",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from e

    signed_url = response.get("signedURL") or response.get("signed_url")
    if not signed_url:
        raise RailMindException(
            code="RM-UPL-005",
            message=f"Supabase returned no signed URL for {storage_path}",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    return signed_url


def file_public_url_if_exists(bucket: str, folder: str, file_name: str) -> str | None:
    """Public URL of folder/file_name in a PUBLIC bucket, or None when missing.
    Checked via the public endpoint (HEAD) — works without any RLS policy,
    unlike the storage list API."""
    public_url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/public/"
        f"{bucket}/{folder}/{file_name}"
    )
    response = httpx.head(public_url, timeout=15)
    if response.status_code == status.HTTP_200_OK:
        return public_url
    return None


def upload_public_file(
    bucket: str, storage_path: str, file_bytes: bytes, content_type: str
) -> str:
    """Uploads (upsert) to an arbitrary bucket/path and returns the public URL."""
    client = get_supabase_client()
    try:
        client.storage.from_(bucket).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    except Exception as e:
        raise RailMindException(
            code="RM-UPL-003",
            message=f"Supabase upload failed: {str(e)}",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from e

    return client.storage.from_(bucket).get_public_url(storage_path)
