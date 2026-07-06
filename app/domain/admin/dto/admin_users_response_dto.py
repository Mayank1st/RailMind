from datetime import date, datetime

from app.schemas.base import BaseDTO


# -- AdminUserSummary (one list row) -----------------------------
class AdminUserSummaryDTO(BaseDTO):
    user_id: str
    name: str | None  # USER column (name); falls back to username
    email: str
    role: str  # backend value: USER | AGENT | ADMIN
    role_label: str  # UI label: USER | Support | Super
    kyc_status: str | None  # PASSED | PENDING | FAILED (null = no KYC record)
    bookings_count: int
    is_active: bool
    status: str  # "active" | "suspended"


# -- AdminUserDetail (drawer) ------------------------------------
class AdminUserDetailResponseDTO(BaseDTO):
    user_id: str
    name: str | None
    email: str
    phone: str | None
    joined_at: date | datetime | None  # "Joined"
    lifetime_bookings: int
    role: str
    role_label: str
    is_active: bool
    status: str
    kyc_status: str | None
    kyc_document_type: str | None  # "PAN" | "Aadhaar" (null if no doc)
    kyc_document_masked: str | None  # masked number, e.g. "XXXXXX1234F"
    kyc_verified_at: datetime | None


# -- AdminUsersSummaryStats (the 4 tiles) ------------------------
class AdminUsersSummaryStatsDTO(BaseDTO):
    total_users: int
    kyc_passed: int
    kyc_pending: int
    kyc_failed: int
