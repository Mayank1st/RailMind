from datetime import date

from app.schemas.base import BaseDTO


# -- TrendingRoute --------------------------------------------------
class TrendingRouteResponseDTO(BaseDTO):
    demand_level: str  # HIGH | MEDIUM | LOW
    source_station_code: str
    source_station_name: str
    destination_station_code: str
    destination_station_name: str
    train_number: str | None  # representative (fastest) train on the route
    train_name: str | None
    avg_duration_minutes: int | None  # mean across trains on the route
    min_fare: float | None  # cheapest class total — the "from ₹X" price
    search_count: int


# -- WeeklyTrending --------------------------------------------------
class WeeklyTrendingResponseDTO(BaseDTO):
    week_start: date | None  # None when no week has been computed yet
    routes: list[TrendingRouteResponseDTO]


# -- PopularDestination --------------------------------------------------
class PopularDestinationResponseDTO(BaseDTO):
    rank: int  # 1 = most searched
    destination_station_code: str
    destination_station_name: str
    origin_station_code: str  # top origin searchers come from
    origin_station_name: str
    trains_count: int | None  # trains on the origin->destination corridor
    train_number: str | None  # representative (fastest) train
    train_name: str | None
    min_fare: float | None  # the "from ₹X" price
    tagline: str | None  # LLM-generated; train-type fallback
    image_url: str | None  # weekly carousel image (Supabase public URL)
    search_count: int


# -- WeeklyPopularDestinations --------------------------------------------------
class WeeklyPopularDestinationsResponseDTO(BaseDTO):
    week_start: date | None  # None when no week has been computed yet
    destinations: list[PopularDestinationResponseDTO]
