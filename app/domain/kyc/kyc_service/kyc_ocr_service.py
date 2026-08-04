import io
import logging
import uuid

from fastapi import UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.core.exceptions import RailMindException
from app.domain.kyc.constants.kyc import (
    ALLOWED_KYC_IMAGE_TYPES,
    BYTES_PER_MB,
    DOCUMENT_FIELDS,
    DOCUMENT_KEY_FIELD,
    ERR_IMAGE_TOO_LARGE,
    ERR_IMAGE_UNREADABLE,
    ERR_INVALID_IMAGE_TYPE,
    ERR_NOTHING_EXTRACTED,
    ERR_OCR_FAILED,
    JPEG_QUALITY,
    MAX_IMAGE_EDGE_PX,
    MAX_KYC_IMAGE_MB,
    NORMALISED_CONTENT_TYPE,
    NORMALISED_EXTENSION,
    SIGNED_URL_TTL_SECONDS,
    DocumentType,
)
from app.integrations.ocr import OcrExtractionError, extract_document_fields
from app.integrations.supabase_client import create_signed_url, upload_private_file
from app.utils.helpers import get_content_type

logger = logging.getLogger(__name__)


class KycOcrService:
    """
    Reads an Aadhaar / PAN image and returns the fields for the user to confirm.

    Deliberately writes nothing to `user_kyc` and never touches `kyc_status` — the
    user confirms via PATCH /auth/profile and an admin approves. The AI's only job
    is saving the user from typing a 12-digit number off a card.
    """

    @staticmethod
    def _validate(file_bytes: bytes) -> None:
        size_mb = len(file_bytes) / BYTES_PER_MB
        if size_mb > MAX_KYC_IMAGE_MB:
            raise RailMindException(
                code=ERR_IMAGE_TOO_LARGE,
                message=f"File size {size_mb:.2f}MB exceeds the {MAX_KYC_IMAGE_MB}MB limit",
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Sniffed from the bytes, not the client-supplied content-type.
        content_type = get_content_type(file_bytes=file_bytes)
        if content_type not in ALLOWED_KYC_IMAGE_TYPES:
            raise RailMindException(
                code=ERR_INVALID_IMAGE_TYPE,
                message=f"Invalid file type: {content_type}. Allowed: JPEG, PNG, WebP",
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

    @staticmethod
    def _normalise(file_bytes: bytes) -> bytes:
        """Downscale and re-encode as JPEG. The re-encode is the point as much as
        the resize: it drops EXIF, and a phone photo of an ID card carries GPS."""
        try:
            image = Image.open(io.BytesIO(file_bytes))
            image.load()
        except (UnidentifiedImageError, OSError) as e:
            raise RailMindException(
                code=ERR_IMAGE_UNREADABLE,
                message="That image could not be read. Try a clearer photo.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            ) from e

        image = image.convert("RGB")  # also drops alpha, which JPEG can't hold
        image.thumbnail((MAX_IMAGE_EDGE_PX, MAX_IMAGE_EDGE_PX))

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        return buffer.getvalue()

    @staticmethod
    def _storage_path(current_user_id: str) -> str:
        return (
            f"{settings.SUPABASE_KYC_FOLDER}/{current_user_id}/"
            f"{uuid.uuid4()}{NORMALISED_EXTENSION}"
        )

    async def extract(
        self,
        document: UploadFile,
        document_type: DocumentType,
        current_user_id: str,
    ) -> dict:
        file_bytes = await document.read()
        self._validate(file_bytes)
        normalised = self._normalise(file_bytes)

        storage_path = self._storage_path(current_user_id)
        upload_private_file(
            bucket=settings.SUPABASE_KYC_BUCKET,
            storage_path=storage_path,
            file_bytes=normalised,
            content_type=NORMALISED_CONTENT_TYPE,
        )
        signed_url = create_signed_url(
            bucket=settings.SUPABASE_KYC_BUCKET,
            storage_path=storage_path,
            expires_in=SIGNED_URL_TTL_SECONDS,
        )

        try:
            fields = await extract_document_fields(signed_url, document_type.value)
        except OcrExtractionError as e:
            # Unlike the advisor endpoints, this surfaces. An empty read presented as
            # success looks like a blank card; the user needs to know to type it in.
            logger.warning(
                "%s OCR failed | type=%s path=%s",
                ERR_OCR_FAILED,
                document_type.value,
                storage_path,
            )
            raise RailMindException(
                code=ERR_OCR_FAILED,
                message="Could not read the document right now. Please enter the details manually.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from e

        # The document is worthless to the user if the one number they came for is
        # missing — say so instead of returning a shell of nulls.
        if not fields.get(DOCUMENT_KEY_FIELD[document_type.value]):
            raise RailMindException(
                code=ERR_NOTHING_EXTRACTED,
                message=(
                    f"Couldn't read the {document_type.value} number from that image. "
                    "Try a sharper, well-lit photo of the full card."
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return {
            "document_type": document_type,
            "document_path": storage_path,
            "fields": fields,
            "unreadable_fields": [
                field
                for field in DOCUMENT_FIELDS[document_type.value]
                if not fields.get(field)
            ],
        }
