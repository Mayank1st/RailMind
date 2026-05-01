from fastapi import Depends, HTTPException
from app.core.constants.auth_user import UserRole
from app.api.deps import get_current_user


# ─── Role Hierarchy ──────────────────────────────────────────────────────────
# Higher index = more permissions
ROLE_HIERARCHY = {
    UserRole.GUEST: 0,
    UserRole.USER: 1,
    UserRole.AGENT: 2,
    UserRole.ADMIN: 3,
}


def has_minimum_role(user_role: str, required_role: UserRole) -> bool:
    """Check if user's role meets the minimum required role."""
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY[required_role]


# ─── Role Dependency Factories ───────────────────────────────────────────────
# Use these as Depends() in your routes


def require_role(*allowed_roles: UserRole):
    async def _check(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role")
        if user_role not in [r.value for r in allowed_roles]:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return _check


def require_minimum_role(role: UserRole):
    async def _check(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role")
        if not has_minimum_role(user_role, role):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Minimum required role: {role.value}",
            )
        return current_user

    return _check


# ─── Prebuilt Role Dependencies ───────────────────────────────────────────────
# Import and use these directly in routes for cleaner code

IsUser = Depends(require_minimum_role(UserRole.USER))
IsAgent = Depends(require_minimum_role(UserRole.AGENT))
IsAdmin = Depends(require_minimum_role(UserRole.ADMIN))
