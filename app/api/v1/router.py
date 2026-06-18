from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    booking,
    complaint,
    fare,
    health,
    notification,
    passenger,
    payment,
    pnr,
    train,
    waitlist,
    common,
    faq,
    search_history,
    station,
    live_status,
)

router = APIRouter()

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(booking.router)
router.include_router(train.router)
router.include_router(passenger.router)
router.include_router(payment.router)
router.include_router(pnr.router)
router.include_router(notification.router)
router.include_router(waitlist.router)
router.include_router(fare.router)
router.include_router(complaint.router)
router.include_router(admin.router)
router.include_router(common.router)
router.include_router(faq.router)
router.include_router(search_history.router)
router.include_router(station.router)
router.include_router(live_status.router)
