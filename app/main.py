from fastapi import FastAPI
from app.routes.health_check import router as health_check_router
from app.utils.helper.get_utc import get_utc_timezone

app = FastAPI()
app.include_router(health_check_router)


# Home Route
@app.get('/',tags=["Home"])
async def home_route():
    res={
        "Name" : "RailMind-BE",
        "Version" : "1.0",
        "Creator" : "Mayank Kumar",
        "Time" : get_utc_timezone ()
    }
    return res