from enum import Enum
from typing import Union

# ─── Rate Limiting ────────────────────────────────────────────────────────────

RATE_LIMIT_SEARCH_PER_MINUTE = 30
RATE_LIMIT_BOOKING_PER_MINUTE = 5

# ─── Cache TTLs (seconds) ─────────────────────────────────────────────────────

CACHE_TTL_TRAIN_SCHEDULE = 3600  # 1 hour  — schedule rarely changes
CACHE_TTL_SEAT_AVAILABILITY = 60  # 1 min   — high churn during booking window
CACHE_TTL_FARE = 300  # 5 mins
CACHE_TTL_AI_PREDICTION = 900  # 15 mins


class KycStatus(str, Enum):
    PASSED = "PASSED"
    PENDING = "PENDING"
    FAILED = "FAILED"


class OccupationType(str, Enum):
    GOVERNMENT_SECTOR = "GOVERNMENT_SECTOR"
    CORPORATE_OR_PRIVATE = "CORPORATE_OR_PRIVATE"
    EDUCATION = "EDUCATION"
    BUSINESS_AND_SELF_EMPLOYED = "BUSINESS_AND_SELF_EMPLOYED"
    SKILLED_AND_SERVICE = "SKILLED_AND_SERVICE"
    OTHERS = "OTHERS"


class GovernmentSector(str, Enum):
    PSU_EMPLOYEE = "PSU_EMPLOYEE"
    ARMED_FORCES = "ARMED_FORCES"
    POLICE_PARAMILITARY = "POLICE_PARAMILITARY"
    JUDICIARY = "JUDICIARY"


class CorporateOrPrivateSector(str, Enum):
    IT_PROFESSIONAL = "IT_PROFESSIONAL"
    ENGINEER = "ENGINEER"
    DOCTOR = "DOCTOR"
    CHARTERED_ACCOUNTANT = "CHARTERED_ACCOUNTANT"
    LAWYER = "LAWYER"
    BANKER = "BANKER"
    CONSULTANT = "CONSULTANT"
    MARKETING_PROFESSIONAL = "MARKETING_PROFESSIONAL"


class EducationSector(str, Enum):
    STUDENT = "STUDENT"
    TEACHER = "TEACHER"
    PROFESSOR = "PROFESSOR"
    RESEARCH_SCHOLAR = "RESEARCH_SCHOLAR"


class BussinessAndSelfEmployeed(str, Enum):
    BUSSINESS_OWNER = "BUSSINESS_OWNER"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    FREELANCER = "FREELANCER"
    ENTERPRENEUR = "ENTERPRENEUR"
    TRADER = "TRADER"


class SkilledAndService(str, Enum):
    FARMER = "FARMER"
    TECHNICIAN = "TECHNICIAN"
    DRIVER = "DRIVER"
    SKILLED_WORKER = "SKILLED_WORKER"
    TOURISM = "TOURISM"


AllOccupations = Union[
    GovernmentSector,
    CorporateOrPrivateSector,
    EducationSector,
    BussinessAndSelfEmployeed,
    SkilledAndService,
]


class MaritalStatus(str, Enum):
    MARRIED = "MARRIED"
    UNMARRIED = "UNMARRIED"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    TRANSGENDER = "TRANSGENDER"


class UserRole(str, Enum):
    GUEST = "GUEST"  # unauthenticated — not stored in DB, used in logic
    USER = "USER"  # default registered passenger
    AGENT = "AGENT"  # travel agent
    ADMIN = "ADMIN"  # full system access


# Cookie names
ACCESS_TOKEN_COOKIE_NAME = "access_token"
REFRESH_TOKEN_COOKIE_NAME = "refresh_token"
CSRF_TOKEN_COOKIE_NAME = "csrf_token"

# Refresh token only travels to this path — reduces exposure
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/auth/refresh"
