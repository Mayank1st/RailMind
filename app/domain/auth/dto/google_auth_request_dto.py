from app.schemas.base import BaseDTO


# -- GoogleAuthRequest ---------------------------------------
class GoogleAuthRequestDTO(BaseDTO):
    id_token: str
