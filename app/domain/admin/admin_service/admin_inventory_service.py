from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Row, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.train import SeatInventories, Trains
from app.domain.admin.constants.admin_inventory import (
    CHART_LABEL_NOT_PREPARED,
    CHART_LABEL_PREPARED,
    DEFAULT_UPCOMING_WINDOW_DAYS,
)
from app.domain.admin.dto.admin_inventory_response_dto import (
    AdminInventorySummaryDTO,
)


class AdminInventoryService:
    # ── Reads ───────────────────────────────────────────────────────────────

    async def list_inventory(
        self,
        db: AsyncSession,
        search: Optional[str],
        train_class: Optional[str],
        quota: Optional[str],
        journey_date_from: Optional[date],
        journey_date_to: Optional[date],
        chart_prepared: Optional[bool],
        min_wl_depth: Optional[int],
        page: int,
        size: int,
    ) -> tuple[list[AdminInventorySummaryDTO], int]:
        journey_date_from, journey_date_to = self._resolve_window(
            journey_date_from, journey_date_to
        )

        # Row-level filters (applied before grouping). `search` is pushed down as
        # a train_id IN (…) subquery so the heavy group-by never has to join
        # `trains` — that join is what made the paginated count multi-second.
        conditions = [
            SeatInventories.journey_date >= journey_date_from,
            SeatInventories.journey_date <= journey_date_to,
        ]
        if search:
            like = f"%{search.strip()}%"
            conditions.append(
                SeatInventories.train_id.in_(
                    select(Trains.id).where(
                        or_(
                            Trains.train_number.ilike(like),
                            Trains.train_name.ilike(like),
                        )
                    )
                )
            )
        if train_class:
            conditions.append(SeatInventories.train_class == train_class)
        if quota:
            conditions.append(SeatInventories.quota == quota)

        chart_prepared_expr = func.bool_and(SeatInventories.is_chart_prepared)
        wl_depth_expr = func.max(SeatInventories.wl_count)

        grouped = (
            select(
                SeatInventories.train_id.label("train_id"),
                SeatInventories.journey_date.label("journey_date"),
                SeatInventories.train_class.label("train_class"),
                func.sum(SeatInventories.total_confirmed_seats).label("cap"),
                func.sum(
                    SeatInventories.total_confirmed_seats
                    - SeatInventories.available_confirmed_seats
                ).label("booked"),
                func.sum(SeatInventories.available_confirmed_seats).label("available"),
                func.sum(SeatInventories.available_rac_slots).label("available_rac"),
                wl_depth_expr.label("wl_depth"),
                chart_prepared_expr.label("chart_prepared"),
            )
            .where(and_(*conditions))
            .group_by(
                SeatInventories.train_id,
                SeatInventories.journey_date,
                SeatInventories.train_class,
            )
        )

        # Aggregate-level filters (applied after grouping).
        if chart_prepared is not None:
            grouped = grouped.having(chart_prepared_expr.is_(chart_prepared))
        if min_wl_depth is not None:
            grouped = grouped.having(wl_depth_expr >= min_wl_depth)

        grouped_subq = grouped.subquery()
        total = await db.scalar(select(func.count()).select_from(grouped_subq))

        # Join `trains` only onto the grouped result (for the display names) and
        # order there. Furthest-out journey first, then by train — matches the FE.
        page_query = (
            select(
                grouped_subq,
                Trains.train_number.label("train_number"),
                Trains.train_name.label("train_name"),
            )
            .join(Trains, Trains.id == grouped_subq.c.train_id)
            .order_by(
                grouped_subq.c.journey_date.desc(),
                Trains.train_number.asc(),
                grouped_subq.c.train_class.asc(),
            )
            .limit(size)
            .offset((page - 1) * size)
        )
        rows = (await db.execute(page_query)).all()
        items = [self._serialize_row(row) for row in rows]
        return items, int(total or 0)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_window(
        journey_date_from: Optional[date], journey_date_to: Optional[date]
    ) -> tuple[date, date]:
        """No journey_date filter at all → bound to the next N days so the
        grouped count stays fast. Any explicit bound is honoured as given."""
        if journey_date_from is None and journey_date_to is None:
            today = datetime.now(timezone.utc).date()
            return today, today + timedelta(days=DEFAULT_UPCOMING_WINDOW_DAYS)
        return (
            journey_date_from or date.min,
            journey_date_to or date.max,
        )

    @staticmethod
    def _serialize_row(row: Row) -> AdminInventorySummaryDTO:
        return AdminInventorySummaryDTO(
            train_id=str(row.train_id),
            train_number=row.train_number,
            train_name=row.train_name,
            journey_date=row.journey_date,
            train_class=row.train_class,
            booked_confirmed_seats=int(row.booked or 0),
            total_confirmed_seats=int(row.cap or 0),
            available_confirmed_seats=int(row.available or 0),
            available_rac_slots=int(row.available_rac or 0),
            wl_depth=int(row.wl_depth or 0),
            is_chart_prepared=bool(row.chart_prepared),
            chart_label=(
                CHART_LABEL_PREPARED if row.chart_prepared else CHART_LABEL_NOT_PREPARED
            ),
        )
