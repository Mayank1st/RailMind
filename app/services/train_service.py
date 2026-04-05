from app.schemas.train import SearchTrainDTO
from app.integrations.rapidapi import rapidapi_client

from app.core.exceptions import RailMindException


class TrainService:

    async def search_trains(self, payload: SearchTrainDTO) -> dict:
        try:
            data = await rapidapi_client(
                payload.fromStationCode,
                payload.toStationCode,
                payload.hours,
            )

            return {
                "data": data
            }

        except Exception as e:
            raise RailMindException(
                code="RM-TRAIN-001",
                message="Failed to fetch train data",
                status_code=500,
            )