import os
from supabase import create_client, Client
from app.config import settings


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
