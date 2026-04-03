from app.utils.helpers import get_utc_timezone


class HealthCheckService:

    @staticmethod
    async def get_health_check_status():
        return {
            "status": "Working",
            "timestamp": get_utc_timezone(),
        }
