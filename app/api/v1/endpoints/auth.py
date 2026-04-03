from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.auth import ContactDetails
from app.services.auth_service import AuthService
from app.core.response import APIResponse, created

router = APIRouter(prefix="/auth", tags=["Auth"])

auth_service = AuthService()


@router.post("/register")
async def create_user_account(
    payload: ContactDetails, db: AsyncSession = Depends(get_db)
):
    data = await auth_service.create_user_account(payload, db)
    return created(data=data, message="Account created. Please verify your email.")
