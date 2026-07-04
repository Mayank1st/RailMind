import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models.station_clusters import StationClusterMembers, StationClusters
from app.db.models.train import Stations
from app.db.session import async_session_local

logger = logging.getLogger(__name__)


class StationClusterService:
    def __init__(self) -> None:
        self._loaded = False
        self._station_to_cluster: dict[str, str] = {}  # "BCT" -> "MUMBAI"
        self._clusters: dict[str, dict] = {}  # "MUMBAI" -> {code,name,primary,members}

    # ── Loading ───────────────────────────────────────────────────────────────

    async def load(self, db: AsyncSession, *, force: bool = False) -> None:
        if self._loaded and not force:
            return

        PRIMARY = aliased(Stations)
        MEMBER = aliased(Stations)
        rows = (
            await db.execute(
                select(
                    StationClusters.cluster_code,
                    StationClusters.cluster_name,
                    PRIMARY.station_code.label("primary_code"),
                    PRIMARY.station_name.label("primary_name"),
                    MEMBER.station_code.label("member_code"),
                    MEMBER.station_name.label("member_name"),
                )
                .select_from(StationClusters)
                .join(PRIMARY, PRIMARY.id == StationClusters.primary_station_id)
                .join(
                    StationClusterMembers,
                    StationClusterMembers.cluster_id == StationClusters.id,
                )
                .join(MEMBER, MEMBER.id == StationClusterMembers.station_id)
            )
        ).all()

        clusters: dict[str, dict] = {}
        station_to_cluster: dict[str, str] = {}
        for r in rows:
            cluster = clusters.setdefault(
                r.cluster_code,
                {
                    "cluster_code": r.cluster_code,
                    "cluster_name": r.cluster_name,
                    "primary_station": {"code": r.primary_code, "name": r.primary_name},
                    "members": [],
                },
            )
            cluster["members"].append({"code": r.member_code, "name": r.member_name})
            station_to_cluster[r.member_code] = r.cluster_code

        self._clusters = clusters
        self._station_to_cluster = station_to_cluster
        self._loaded = True
        logger.info(
            "station clusters loaded: %s clusters, %s member stations",
            len(clusters),
            len(station_to_cluster),
        )

    async def ensure_loaded(self, db: AsyncSession) -> None:
        if not self._loaded:
            await self.load(db)

    async def reload(self, db: AsyncSession) -> None:
        await self.load(db, force=True)

    # ── Lookups (in-memory, O(1)) ─────────────────────────────────────────────

    def expand_station_set(self, station_code: str) -> set[str]:
        """
        All station codes in `station_code`'s cluster (incl. itself). If the
        station isn't clustered, returns just `{station_code}` — so callers can
        use the result unconditionally.
        """
        code = (station_code or "").upper()
        cluster_code = self._station_to_cluster.get(code)
        if not cluster_code:
            return {code}
        members = {m["code"] for m in self._clusters[cluster_code]["members"]}
        members.add(code)
        return members

    def get_cluster_for_station(self, station_code: str) -> dict | None:
        return self._clusters.get(
            self._station_to_cluster.get((station_code or "").upper(), "")
        )

    async def get_cluster_view(self, db: AsyncSession, station_code: str) -> dict:
        await self.ensure_loaded(db)
        code = (station_code or "").upper()
        cluster = self.get_cluster_for_station(code)
        if not cluster:
            return {
                "station_code": code,
                "in_cluster": False,
                "cluster_code": None,
                "cluster_name": None,
                "primary_station": None,
                "members": [],
                "also_covered": [],
            }
        also_covered = [m["code"] for m in cluster["members"] if m["code"] != code]
        return {
            "station_code": code,
            "in_cluster": True,
            "cluster_code": cluster["cluster_code"],
            "cluster_name": cluster["cluster_name"],
            "primary_station": cluster["primary_station"],
            "members": cluster["members"],
            "also_covered": also_covered,
        }


station_cluster_service = StationClusterService()


async def preload_station_clusters() -> None:
    """
    Warm the in-memory cluster map at app startup. Best-effort — never blocks
    boot if the table is empty/unmigrated (lazy `ensure_loaded` is the fallback).
    """
    try:
        async with async_session_local() as db:
            await station_cluster_service.load(db, force=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("station cluster cache not loaded: %s", exc)
