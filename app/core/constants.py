from enum import Enum
from typing import Union


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

