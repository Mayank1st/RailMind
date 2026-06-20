---
name: railmind-conventions
description: RailMind FastAPI backend coding conventions — folder/file naming, router file layout, service classes, DTO naming and structure, SQLAlchemy models, and enums. Use whenever writing or editing any Python in the RailMind backend, and before committing backend changes.
---

# RailMind backend conventions

Follow these whenever you write or edit backend Python. They are mandatory and
consistent across the codebase. Write compliant code from the start.

## 1. Folders and files

- **Folders are `snake_case`.** Two words -> `log_file`. Single word -> `log`.
  Never `logFile`, `log_File`, or `Log_File`.
- **Every folder has an `__init__.py`** (it is a Python package).
- **`.py` files are `snake_case`** -> `train_service.py`, `fare_calculator.py`.
  Never `TrainService.py` or `trainService.py`.

## 2. Module layout (order inside a file)

Every module follows this top-to-bottom order:

1. **Imports** — `import ...` statements first, then `from ... import ...`.
2. **Constants** — directly below imports, `UPPER_SNAKE`, only if the file needs them.
3. **Router** — `router = APIRouter(...)` (router files only).
4. **Service instance** — e.g. `auth_service = AuthService()` (if used).
5. **Endpoints / definitions.**

### Import rules

- `import` group first, then a blank line, then the `from ... import` group.
- Order within: standard library -> third-party -> local app imports.
- **No wildcard imports** (`from x import *`).

```python
import logging

from fastapi import APIRouter, Depends

from app.domain.auth.service import AuthService
from app.domain.auth.dto.auth_request_dto import LoginRequestDTO
```

## 3. Routers

- **Tag starts with a capital letter; prefix is lowercase.**
  `router = APIRouter(prefix="/auth", tags=["Auth"])`
- **Endpoint paths are lowercase** -> `/login`, `/otp-verify`.
  Multi-word paths use kebab-case. All routes live under `/api/v1/`
  (AI routes under `/api/v1/ai/`).
- **Routers are thin** — no business logic in the endpoint. Validate, call the
  service, return. All logic lives in the service layer.
- Every response is wrapped in the `APIResponse` envelope.

```python
import logging

from fastapi import APIRouter

from app.domain.auth.service import AuthService
from app.domain.auth.dto.auth_request_dto import LoginRequestDTO

OTP_LENGTH = 6

router = APIRouter(prefix="/auth", tags=["Auth"])

auth_service = AuthService()


@router.post("/login")
async def login_user(payload: LoginRequestDTO):
    ...
```

## 4. Services

- Each service file defines a **class** named in `PascalCase` with a
  `Service` suffix -> `AuthService`, `BookingService`, `FareService`.
- Functions inside are `snake_case` verb_noun -> `create_booking`,
  `calculate_fare`, `verify_otp`.
- Services hold no per-request state; pass the DB session in per call rather
  than storing it on the instance.

```python
class AuthService:
    async def verify_otp(self, phone: str, code: str) -> bool:
        ...
```

## 5. DTOs

- **File names end with `dto`** and stay `snake_case` ->
  `auth_request_dto.py`, `booking_response_dto.py`.
- **Request DTO class -> `<Name>RequestDTO`.** Response DTO class ->
  `<Name>ResponseDTO`. -> `LoginRequestDTO`, `BookingResponseDTO`.
- **Before every DTO class, add a section header comment line:**
  `# -- <Name> --------------------------------------------------`
- **No comments between fields inside a DTO.** Put any note as an
  inline side comment on the same line as the field.
- DTOs are Pydantic v2 models with
  `model_config = ConfigDict(extra="forbid", from_attributes=True)`.
- Every field has an explicit type hint.

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


# -- Autofill --------------------------------------------------
class AutofillRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    user_id: str
    confidence: Literal["high", "medium", "low"] = "low"  # default to low


# -- Autofill --------------------------------------------------
class AutofillResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    predicted_class: str
    confidence: float  # 0.0-1.0
```

## 6. Models (SQLAlchemy 2.0)

- **Model class names are plural** -> `Bookings`, `Seats`, `Coaches`
  (matches the table name).
- **Every model ends with a `__repr__`:** `def __repr__(self) -> str:`.
- Columns use `Mapped[T]` with `mapped_column()`.
- `__tablename__` is plural `snake_case`; `__table_args__` is a tuple that
  ends with `{"schema": DB_SCHEMA}`.
- Foreign keys use the `f"{DB_SCHEMA}.table.id"` format.
- Every model inherits `BaseModel` (`id` UUID, `created_at`, `updated_at`).
- Relationships use two-way `back_populates` on both sides.

```python
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel
from app.core.constants import DB_SCHEMA


class Bookings(BaseModel):
    __tablename__ = "bookings"
    __table_args__ = ({"schema": DB_SCHEMA},)

    pnr_number: Mapped[str] = mapped_column(unique=True)
    booking_status: Mapped[str] = mapped_column()
    user_id: Mapped[str] = mapped_column(ForeignKey(f"{DB_SCHEMA}.users.id"))

    def __repr__(self) -> str:
        return f"<Bookings id={self.id} pnr={self.pnr_number}>"
```

## 7. Enums

- Enum classes inherit from `(str, Enum)`.
- Member names are `UPPER_SNAKE`.
- **Stored values are UPPERCASE strings** — the value saved to the database
  must be uppercase. Fix any existing enum whose value is lowercase.

```python
from enum import Enum


class BookingStatus(str, Enum):
    INITIATED = "INITIATED"
    CONFIRMED = "CONFIRMED"
    WAITLISTED = "WAITLISTED"
    CANCELLED = "CANCELLED"
```

## 8. General (prod-level)

- **Type hints on every function** — all parameters and the return type.
- **No magic numbers or strings** in logic — put them in a constants file as
  `UPPER_SNAKE`.
- **Error codes** use the `RM-{DOMAIN}-{NUMBER}` format (e.g. `RM-BKG-001`).
- **Datetimes are timezone-aware** (`DateTime(timezone=True)`).
- **No secrets hardcoded** — read config via `pydantic-settings`.
- IO / DB functions are `async def` and `await` their calls.

## Naming quick reference

| Element | Convention | Example |
| --- | --- | --- |
| Folder | snake_case | `log_file`, `log` |
| File | snake_case | `train_service.py` |
| Function | snake_case verb | `create_booking` |
| Class | PascalCase | `AuthService` |
| Service class | PascalCase + `Service` | `BookingService` |
| Request DTO | `<Name>RequestDTO` | `LoginRequestDTO` |
| Response DTO | `<Name>ResponseDTO` | `BookingResponseDTO` |
| DTO file | snake_case + `_dto` | `auth_request_dto.py` |
| Model class | PascalCase plural | `Bookings` |
| Constant | UPPER_SNAKE | `OTP_LENGTH` |
| Router tag | Capitalized | `tags=["Auth"]` |
| Router prefix / path | lowercase | `prefix="/auth"`, `/login` |
| Enum value | UPPERCASE string | `"CONFIRMED"` |