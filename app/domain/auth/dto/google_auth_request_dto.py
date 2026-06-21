from app.schemas.base import BaseDTO


# -- GoogleAuthRequest ---------------------------------------
class GoogleAuthRequestDTO(BaseDTO):
    id_token: str
    remember_me: bool = False  # ON → persistent login; OFF → session cookie
