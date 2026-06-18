import json
import re
import asyncio
from datetime import datetime, timedelta

from app.services.train_service import TrainService
from app.utils.helpers import parse_datetime_flexible
from sqlalchemy.ext.asyncio import AsyncSession
from app.integrations.gemini_client import gemini_client
from app.ai.prompts.nlp_search_prompts import nlp_search_prompt
from app.schemas.train import CheckSeatAvailabilityDTO, SearchTrainDTO


train_service = TrainService()


class NlpSearchService:

    @staticmethod
    def extract_json_from_llm(text: str) -> dict:
        cleaned = re.sub(r"```json|```", "", text).strip()
        return json.loads(cleaned)

    @staticmethod
    def hours_from_now(target: datetime) -> float:
        now = datetime.now()
        diff = target - now
        return round(diff.total_seconds() / 3600, 2)

    async def get_nlp_search(self, plain_text: str, current_user_id, db: AsyncSession):
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        day_name = today.strftime("%A")

        prompt_response = nlp_search_prompt(
            day_name=day_name,
            today_str=today_str,
            tomorrow_str=tomorrow_str,
            user_query=plain_text,
        )

        response_data = await gemini_client(prompt=prompt_response)
        parsed_data = self.extract_json_from_llm(response_data)

        print("parsed_data===============>", parsed_data)

        journey_date = parsed_data.get("journey_date")

        parsed_hour = None
        if journey_date:
            parsed_datetime = parse_datetime_flexible(journey_date)
            parsed_hour = int(self.hours_from_now(parsed_datetime))
        else:
            parsed_hour = None

        search_train_payload = SearchTrainDTO(
            fromStationCode=parsed_data.get("from_station"),
            toStationCode=parsed_data.get("to_station"),
            hours=parsed_hour,
        )

        # core (un-paginated) variant — NLP enriches the full list itself
        search_train_res = await train_service.search_trains_list(
            search_train_payload, db
        )

        async def enrich(train):
            payload = CheckSeatAvailabilityDTO(
                from_station=train["from_station"],
                to_station=train["to_station"],
                journey_date=journey_date,
                train_class=parsed_data.get("train_class"),
                quota=parsed_data.get("quota"),
            )

            return await train_service.get_seat_availability(
                train["train_number"], payload, db
            )

        search_train_res["trains"] = await asyncio.gather(
            *[enrich(train) for train in search_train_res["trains"]]
        )

        return search_train_res
