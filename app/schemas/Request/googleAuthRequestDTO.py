from pydantic import BaseModel


class GoogleAuthRequestDTO(BaseModel):
    id_token: str
