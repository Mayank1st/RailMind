import httpx
from app.config import settings


async def rapidapi_client(
    fromStationCode: str,
    toStationCode: str | None = None,
    hours: int = 1,
) -> dict:

    url = f"https://{settings.RAPIDAPI_HOST}/api/v3/getLiveStation"

    params = {
        "fromStationCode": fromStationCode,
        "hours": hours,
    }

    if toStationCode:
        params["toStationCode"] = toStationCode

    headers = {
        "x-rapidapi-key": settings.RAPIDAPI_KEY,
        "x-rapidapi-host": settings.RAPIDAPI_HOST,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        return response.json()