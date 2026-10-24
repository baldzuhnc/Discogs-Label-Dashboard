"""Background label sync.

Phase 1 "catalog": page through /labels/{id}/releases (100 per request). That alone
gives title, artist, year, format, cover and want/have for the whole catalogue,
so a 1,000-release label is browsable after ~10 requests.

Phase 2 "details": one /releases/{id} call per release for rating, styles,
marketplace price, videos and tracklist, most promising releases first. With
the 60 req/min limit this is the slow part, so it runs in the background and the
UI updates as it goes.
"""
import asyncio
import math
from dataclasses import asdict, dataclass, field

from .config import CURRENCY, DETAIL_MAX_AGE_DAYS
from .db import DB
from .discogs import Discogs, DiscogsError


@dataclass
class Job:
    label_id: int
    name: str = ""
    phase: str = "queued"  # queued | catalog | details | done | error | cancelled
    done: int = 0
    total: int = 0
    error: str | None = None
    vinyl_only: bool = True
    prices: bool = False
    cancelled: bool = field(default=False, repr=False)

    def public(self):
        d = asdict(self)
        d.pop("cancelled")
        return d


class Syncer:
    def __init__(self, api: Discogs, db: DB):
        self.api = api
        self.db = db
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.jobs: dict[int, Job] = {}
        self._worker: asyncio.Task | None = None

    def start(self):
        self._worker = asyncio.create_task(self._run())

    async def stop(self):
        if self._worker:
            self._worker.cancel()

    def enqueue(self, label_id: int, vinyl_only: bool = True, prices: bool = False) -> Job:
        existing = self.jobs.get(label_id)
        if existing and existing.phase in ("queued", "catalog", "details"):
            return existing
        job = Job(label_id=label_id, vinyl_only=vinyl_only, prices=prices)
        if label := self.db.get_label(label_id):
            job.name = label["name"]
        self.jobs[label_id] = job
        self.queue.put_nowait(job)
        return job

    def cancel(self, label_id: int):
        if job := self.jobs.get(label_id):
            job.cancelled = True
            if job.phase == "queued":
                job.phase = "cancelled"

    async def _run(self):
        while True:
            job = await self.queue.get()
            if job.cancelled:
                continue
            try:
                await self._sync(job)
                job.phase = "cancelled" if job.cancelled else "done"
            except DiscogsError as e:
                job.phase, job.error = "error", str(e)
            except Exception as e:  # keep the worker alive no matter what
                job.phase, job.error = "error", repr(e)

    async def _sync(self, job: Job):
        job.phase = "catalog"
        label = await self.api.label(job.label_id)
        self.db.upsert_label(label)
        job.name = label["name"]

        first = await self.api.label_releases(job.label_id, page=1)
        pages = first["pagination"]["pages"]
        job.total = pages
        self.db.upsert_listing(job.label_id, first["releases"])
        job.done = 1
        for page in range(2, pages + 1):
            if job.cancelled:
                return
            data = await self.api.label_releases(job.label_id, page=page)
            self.db.upsert_listing(job.label_id, data["releases"])
            job.done = page
        self.db.mark_catalog_synced(job.label_id)

        job.phase = "details"
        ids = self.db.releases_needing_detail(job.label_id, job.vinyl_only, DETAIL_MAX_AGE_DAYS)
        job.done, job.total = 0, len(ids)
        for rid in ids:
            if job.cancelled:
                return
            await self.fetch_detail(rid, prices=job.prices)
            job.done += 1

    async def fetch_detail(self, release_id: int, prices: bool = False):
        try:
            data = await self.api.release(release_id)
        except DiscogsError as e:
            if e.status == 404:  # deleted / merged release
                return None
            raise
        data["_currency"] = CURRENCY
        suggestions = await self.api.price_suggestions(release_id) if prices else None
        self.db.upsert_detail(data, suggestions)
        return data


def eta_minutes(job: Job) -> int | None:
    if job.phase != "details":
        return None
    return math.ceil((job.total - job.done) * (1 + job.prices) / 58)
