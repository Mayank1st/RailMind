from app.schemas.base import BaseDTO


# -- GoogleAuthResponse --------------------------------------
class GoogleAuthResponseDTO(BaseDTO):
    user_id: str
    username: str
    email: str
    is_new_user: bool  # True → frontend "Complete your profile" pe bhejega
    suggested_first_name: str | None = None  # Google se — profile prefill ke liye
    suggested_last_name: str | None = None
    picture_url: str | None = None
