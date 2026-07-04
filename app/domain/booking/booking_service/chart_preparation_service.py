import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.constants.booking import PassengerStatus
from app.domain.booking.constants.chart_preparation import (
    CHART_AUTO_CANCEL_CLERKAGE,
    ChartStatus,
)
from app.db.models.booking import BookingPassengers
from app.db.models.train import SeatInventories, TrainStations
from app.db.models.waiting_list import WaitlistEntries
from app.domain.booking.booking_service.booking_service import booking_service
from app.tasks import chart_preparation_tasks as _chart_tasks

logger = logging.getLogger(__name__)
_IST = ZoneInfo("Asia/Kolkata")


class ChartPreparationService:
    """
    2-stage chart preparation, invoked only from Celery tasks.

    Reuses BookingService's production promotion cascade (`_run_promotion_cascade`
    / `_promote_wl_to_rac`) — the same logic that runs on cancellation — so chart
    prep and cancellation can never diverge. Stateless: `db` is passed per call.
    """

    # ── Discovery ─────────────────────────────────────────────────────────────

    async def find_eligible_train_dates(
        self,
        db: AsyncSession,
        *,
        min_hours: int,
        max_hours: int,
        required_status: ChartStatus,
    ) -> list[tuple[UUID, date]]:
        """
        Distinct (train_id, journey_date) whose source departure is in
        [now+min_hours, now+max_hours] and whose chart_status matches.

        Coarse-filters by journey_date (today/tomorrow) using the chart-lookup
        index, then computes the precise departure instant in Python.
        """
        now = datetime.now(_IST)
        today = now.date()

        rows = (
            await db.execute(
                select(
                    SeatInventories.train_id,
                    SeatInventories.journey_date,
                    TrainStations.departure_time,
                    TrainStations.day_number,
                )
                .join(
                    TrainStations,
                    and_(
                        TrainStations.train_id == SeatInventories.train_id,
                        TrainStations.is_source == True,  # noqa: E712
                    ),
                )
                .where(SeatInventories.chart_status == required_status.value)
                .where(
                    SeatInventories.journey_date.in_([today, today + timedelta(days=1)])
                )
                .distinct()
            )
        ).all()

        eligible: set[tuple[UUID, date]] = set()
        for r in rows:
            dep = self._departure_datetime(
                r.journey_date, r.departure_time, r.day_number
            )
            if dep is None:
                continue
            hours_until = (dep - now).total_seconds() / 3600
            if min_hours <= hours_until <= max_hours:
                eligible.add((r.train_id, r.journey_date))
        return list(eligible)

    # ── Per train+date preparation ────────────────────────────────────────────

    async def prepare_chart(
        self, db: AsyncSession, train_id: UUID, journey_date: date, stage: int
    ) -> list[dict]:
        """
        Atomically prepare the chart for one train+date across all its
        class+quota inventory rows. Returns the list of passenger status changes
        (for notifications, fired by the caller / after commit).
        """
        all_changes: list[dict] = []

        async with db.begin():
            inventories = (
                (
                    await db.execute(
                        select(SeatInventories)
                        .where(
                            SeatInventories.train_id == train_id,
                            SeatInventories.journey_date == journey_date,
                        )
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )

            for inv in inventories:
                # Idempotency — only advance from the expected prior status.
                if stage == 1 and inv.chart_status != ChartStatus.NOT_PREPARED.value:
                    continue
                if (
                    stage == 2
                    and inv.chart_status != ChartStatus.STAGE_1_PREPARED.value
                ):
                    continue

                before = await self._snapshot_statuses(db, inv)
                await self._process_inventory(db, inv, stage)
                await db.flush()
                after = await self._snapshot_statuses(db, inv)

                for bp_id, old in before.items():
                    new = after.get(bp_id, old)
                    if new != old:
                        all_changes.append(
                            {
                                "booking_passenger_id": str(bp_id),
                                "old_status": old,
                                "new_status": new,
                            }
                        )

                self._advance_chart_status(inv, stage)

            logger.info(
                "Chart prep S%s done: train=%s date=%s inv=%s changes=%s",
                stage,
                train_id,
                journey_date,
                len(inventories),
                len(all_changes),
            )

        # Commit done (begin() context exit). Notifications outside the txn.
        await self._enqueue_notifications(all_changes, stage)
        return all_changes

    async def _process_inventory(
        self, db: AsyncSession, inv: SeatInventories, stage: int
    ) -> None:
        if stage == 1:
            # RAC → CNF for every free CNF seat (each cascades one WL → RAC)…
            await booking_service._run_promotion_cascade(
                db=db,
                inventory=inv,
                freed_count=inv.available_confirmed_seats,
                allow_wl_to_rac=True,
            )
            # …then fill any RAC slots that are still free (RAC undersold case).
            if inv.available_rac_slots > 0:
                await booking_service._promote_wl_to_rac(
                    db=db, inventory=inv, count=inv.available_rac_slots
                )
            # Everyone still waitlisted → auto-cancelled.
            await self._auto_cancel_remaining_waitlist(db, inv)
        else:
            # Stage 2: RAC → CNF only (waitlist already cleared in Stage 1).
            await booking_service._run_promotion_cascade(
                db=db,
                inventory=inv,
                freed_count=inv.available_confirmed_seats,
                allow_wl_to_rac=False,
            )

    async def _auto_cancel_remaining_waitlist(
        self, db: AsyncSession, inv: SeatInventories
    ) -> None:
        rows = (
            (
                await db.execute(
                    select(WaitlistEntries).where(
                        WaitlistEntries.seat_inventory_id == inv.id,
                        WaitlistEntries.is_promoted == False,  # noqa: E712
                        WaitlistEntries.is_auto_cancelled == False,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )

        now = datetime.now(timezone.utc)
        for wl in rows:
            wl.is_auto_cancelled = True
            wl.auto_cancelled_at = now
            bp = await db.get(BookingPassengers, wl.booking_passenger_id)
            if bp and bp.passenger_status == PassengerStatus.WAITLISTED.value:
                bp.passenger_status = PassengerStatus.AUTO_CANCELLED_CHART.value
                self._log_pending_refund_mock(bp, inv.train_class)

        # All remaining WL are now cleared.
        inv.wl_count = 0

    @staticmethod
    def _advance_chart_status(inv: SeatInventories, stage: int) -> None:
        now = datetime.now(timezone.utc)
        if stage == 1:
            inv.chart_status = ChartStatus.STAGE_1_PREPARED.value
            inv.chart_prepared_stage1_at = now
            # Legacy flag — once Stage 1 runs, cancellations are blocked.
            inv.is_chart_prepared = True
            inv.chart_prepared_at = now
        else:
            inv.chart_status = ChartStatus.FINAL_PREPARED.value
            inv.chart_prepared_stage2_at = now

    # ── Refund (MOCK — see Section 9 / Payment phase) ─────────────────────────

    def _log_pending_refund_mock(self, bp: BookingPassengers, train_class: str) -> None:
        """
        MOCK: real refund creation is deferred to the Payment + Refund phase.

        TODO[payment-phase]: the Refunds model + RefundStatus already exist —
        replace this log with:
            from app.db.models.refund import Refunds
            from app.domain.payment.constants.payment import RefundStatus, RefundReason
            db.add(Refunds(
                booking_id=bp.booking_id,
                refund_amount=float(bp.fare) - clerkage,
                deduction_amount=clerkage,
                refund_status=RefundStatus.PENDING,
                refund_reason=RefundReason....,  # "WL did not confirm at chart prep"
            ))
        """
        clerkage = CHART_AUTO_CANCEL_CLERKAGE.get(train_class, 60)
        refund_amount = max(0.0, float(bp.fare) - clerkage)
        logger.info(
            "[MOCK REFUND PENDING] booking_passenger=%s class=%s fare=%s "
            "clerkage=%s refund_amount=%s",
            bp.id,
            train_class,
            bp.fare,
            clerkage,
            refund_amount,
        )

    # ── Notifications ─────────────────────────────────────────────────────────

    async def _enqueue_notifications(self, changes: list[dict], stage: int) -> None:
        if not changes:
            return
        try:
            for ch in changes:
                _chart_tasks.task_send_chart_notification.delay(
                    booking_passenger_id=ch["booking_passenger_id"],
                    old_status=ch["old_status"],
                    new_status=ch["new_status"],
                    stage=stage,
                )
        except Exception:  # broker down — never fail chart prep on notifications
            logger.warning("failed to enqueue chart notifications", exc_info=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _snapshot_statuses(
        db: AsyncSession, inv: SeatInventories
    ) -> dict[UUID, str]:
        rows = (
            await db.execute(
                select(BookingPassengers.id, BookingPassengers.passenger_status).where(
                    BookingPassengers.seat_inventory_id == inv.id
                )
            )
        ).all()
        return {r.id: r.passenger_status for r in rows}

    @staticmethod
    def _departure_datetime(
        journey_date: date, departure_time: str | None, day_number: int | None
    ) -> datetime | None:
        if not departure_time:
            return None
        try:
            hh, mm = int(departure_time[:2]), int(departure_time[3:5])
        except (ValueError, IndexError):
            return None
        base = datetime(
            journey_date.year,
            journey_date.month,
            journey_date.day,
            hh,
            mm,
            tzinfo=_IST,
        )
        return base + timedelta(days=(day_number or 1) - 1)


chart_preparation_service = ChartPreparationService()
