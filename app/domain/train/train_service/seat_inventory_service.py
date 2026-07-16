from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.booking import BookingPassengers
from app.db.models.train import Coaches, SeatInventories
from app.db.models.waiting_list import WaitlistEntries
from app.domain.train.constants.seat_inventory import (
    INVENTORY_RETENTION_DAYS,
    QUOTA_ALLOCATION,
    RAC_BERTHS_PER_COACH,
    ROLLING_WINDOW_DAYS_AHEAD,
    SEAT_CONFIG,
    SEAT_INVENTORY_BATCH_SIZE,
    WL_MAX,
)
from app.utils.helpers import get_utc_timezone


class SeatInventoryService:
    def _calc_quota_seats(self, confirmed_seats: int, percent: int) -> int:
        if percent == 0:
            return 0
        return max(1, int(confirmed_seats * percent / 100))

    async def extend_rolling_window(self, db: AsyncSession) -> int:
        target_date = date.today() + timedelta(days=ROLLING_WINDOW_DAYS_AHEAD)

        coach_counts_result = await db.execute(
            select(Coaches.train_id, Coaches.train_class, func.count(Coaches.id))
            .where(Coaches.is_active.is_(True))
            .group_by(Coaches.train_id, Coaches.train_class)
        )
        coach_counts = coach_counts_result.all()

        existing_result = await db.execute(
            select(
                SeatInventories.train_id,
                SeatInventories.train_class,
                SeatInventories.quota,
            ).where(SeatInventories.journey_date == target_date)
        )
        existing_keys = {
            (row.train_id, row.train_class, row.quota) for row in existing_result.all()
        }

        inventory_records = []
        for train_id, train_class, coach_count in coach_counts:
            seat_cfg = SEAT_CONFIG.get(train_class)
            if seat_cfg is None:
                continue

            confirmed_seats = seat_cfg["confirmed_seats"] * coach_count
            rac_berths = RAC_BERTHS_PER_COACH.get(train_class, 0) * coach_count
            rac_slots = rac_berths * 2
            quota_alloc = QUOTA_ALLOCATION.get(train_class, QUOTA_ALLOCATION["SL"])

            for quota, percent in quota_alloc.items():
                if (train_id, train_class, quota) in existing_keys:
                    continue

                quota_seats = self._calc_quota_seats(confirmed_seats, percent)
                if quota_seats == 0:
                    continue

                inv_rac_berths = rac_berths if quota == "GN" else 0
                inv_rac_slots = rac_slots if quota == "GN" else 0

                inventory_records.append(
                    {
                        "id": uuid4(),
                        "train_id": train_id,
                        "journey_date": target_date,
                        "train_class": train_class,
                        "quota": quota,
                        "total_confirmed_seats": quota_seats,
                        "available_confirmed_seats": quota_seats,
                        "total_rac_berths": inv_rac_berths,
                        "total_rac_slots": inv_rac_slots,
                        "available_rac_slots": inv_rac_slots,
                        "wl_count": 0,
                        "wl_max": WL_MAX.get(quota, 100),
                        "is_chart_prepared": False,
                        "chart_prepared_at": None,
                        "quota_released_seats": 0,
                        "is_active": True,
                        "created_at": get_utc_timezone(),
                        "updated_at": get_utc_timezone(),
                    }
                )

        inserted = 0
        for i in range(0, len(inventory_records), SEAT_INVENTORY_BATCH_SIZE):
            stmt = (
                pg_insert(SeatInventories)
                .values(inventory_records[i : i + SEAT_INVENTORY_BATCH_SIZE])
                .on_conflict_do_nothing(
                    index_elements=["train_id", "journey_date", "train_class", "quota"]
                )
            )
            result = await db.execute(stmt)
            inserted += result.rowcount

        await db.commit()
        return inserted

    async def prune_expired_inventory(self, db: AsyncSession) -> int:
        cutoff_date = date.today() - timedelta(days=INVENTORY_RETENTION_DAYS)

        has_booking = select(BookingPassengers.id).where(
            BookingPassengers.seat_inventory_id == SeatInventories.id
        )
        has_waitlist_entry = select(WaitlistEntries.id).where(
            WaitlistEntries.seat_inventory_id == SeatInventories.id
        )

        stmt = (
            delete(SeatInventories)
            .where(SeatInventories.journey_date < cutoff_date)
            .where(~has_booking.exists())
            .where(~has_waitlist_entry.exists())
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount
