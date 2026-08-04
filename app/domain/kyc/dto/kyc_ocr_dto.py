from typing import Annotated, Optional

from pydantic import Field

from app.domain.kyc.constants.kyc import DocumentType
from app.schemas.base import BaseDTO


# -- ExtractedKycFields --------------------------------------
class ExtractedKycFieldsDTO(BaseDTO):
    name: Optional[Annotated[str, Field(examples=["RAHUL SHARMA"])]] = None
    date_of_birth: Optional[Annotated[str, Field(examples=["1995-04-12"])]] = (
        None  # as printed, unvalidated
    )
    aadhaar_number: Optional[Annotated[str, Field(examples=["123412341234"])]] = (
        None  # AADHAAR only
    )
    gender: Optional[Annotated[str, Field(examples=["MALE"])]] = None  # AADHAAR only
    pan_number: Optional[Annotated[str, Field(examples=["ABCDE1234F"])]] = (
        None  # PAN only
    )
    father_name: Optional[Annotated[str, Field(examples=["SURESH SHARMA"])]] = (
        None  # PAN only
    )


# -- KycOcrResponse ------------------------------------------
class KycOcrResponseDTO(BaseDTO):
    document_type: DocumentType
    document_path: Annotated[
        str, Field(examples=["kyc/<user-id>/<uuid>.jpg"])
    ]  # private bucket, not a URL
    fields: ExtractedKycFieldsDTO
    unreadable_fields: list[str] = (
        []
    )  # asked for, came back null — user must type these
