from fastapi import APIRouter

from app.domain.admin.admin_router.admin import router as admin_router
from app.domain.auth.auth_router.auth import router as auth_router
from app.domain.booking.booking_router.booking import router as booking_router
from app.domain.common.common_router.common import router as common_router
from app.domain.complaint.complaint_router.complaint import router as complaint_router
from app.domain.faq.faq_router.faq import router as faq_router
from app.domain.fare.fare_router.fare import router as fare_router
from app.domain.health.health_router.health_check import router as health_router
from app.domain.live_status.live_status_router.live_status import (
    router as live_status_router,
)
from app.domain.notification.notification_router.notification import (
    router as notification_router,
)
from app.domain.passenger.passenger_router.passenger import router as passenger_router
from app.domain.payment.payment_router.payments import router as payment_router
from app.domain.pnr.pnr_router.pnr import router as pnr_router
from app.domain.search_history.search_history_router.search_history import (
    router as search_history_router,
)
from app.domain.station.station_router.stations import router as station_router
from app.domain.train.train_router.train import router as train_router
from app.domain.waitlist.waitlist_router.waitlist import router as waitlist_router

router = APIRouter()

router.include_router(health_router)
router.include_router(auth_router)
router.include_router(booking_router)
router.include_router(train_router)
router.include_router(passenger_router)
router.include_router(payment_router)
router.include_router(pnr_router)
router.include_router(notification_router)
router.include_router(waitlist_router)
router.include_router(fare_router)
router.include_router(complaint_router)
router.include_router(admin_router)
router.include_router(common_router)
router.include_router(faq_router)
router.include_router(search_history_router)
router.include_router(station_router)
router.include_router(live_status_router)
