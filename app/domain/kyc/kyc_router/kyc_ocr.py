from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_current_user, rate_limit
from app.core.response import ok
from app.domain.kyc.constants.kyc import (
    RATE_LIMIT_PER_MINUTE,
    RATE_LIMIT_SCOPE,
    DocumentType,
)
from app.domain.kyc.dto.kyc_ocr_dto import KycOcrResponseDTO
from app.domain.kyc.kyc_service.kyc_ocr_service import KycOcrService

router = APIRouter(prefix="/kyc", tags=["KYC OCR"])

kyc_ocr_service = KycOcrService()


@router.post(
    "/extract",
    dependencies=[
        Depends(rate_limit(limit=RATE_LIMIT_PER_MINUTE, scope=RATE_LIMIT_SCOPE))
    ],
)
async def extract_kyc_document(
    document: UploadFile = File(..., description="Photo of the Aadhaar / PAN card"),
    document_type: DocumentType = Form(..., description="AADHAAR | PAN"),
    current_user: dict = Depends(get_current_user),
):
    data = await kyc_ocr_service.extract(
        document=document,
        document_type=document_type,
        current_user_id=current_user["sub"],
    )
    return ok(
        data=KycOcrResponseDTO.model_validate(data),
        message="Document read successfully. Please confirm the details.",
        meta={"unreadable_count": len(data["unreadable_fields"])},
    )
