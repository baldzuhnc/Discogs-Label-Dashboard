import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import CURRENCY, DB_PATH, DISCOGS_TOKEN, LEGACY_DATA
from .db import DB
from .discogs import Discogs, DiscogsError
from .legacy_import import import_legacy
from .scoring import label_summary, score_releases
from .sync import Syncer, eta_minutes

STATIC = Path(__file__).parent / "static"
JSON_FIELDS = ("genres", "styles", "videos", "tracklist", "formats", "price_suggestions")
# Fields the grid needs; the heavy stuff (tracklist, notes, videos) is only sent per release.
LIST_FIELDS = (
    "id", "title", "artist", "year", "thumb", "image", "format", "catno", "is_vinyl", "want", "have",
    "user_want", "user_have", "rating_avg", "rating_count", "lowest_price", "num_for_sale", "styles",
    "country", "master_id", "dig", "ratio", "raw_ratio", "tags", "detail_at", "n_videos",
)


def _decode(row: dict) -> dict:
    for f in JSON_FIELDS:
        if isinstance(row.get(f), str):
            row[f] = json.loads(row[f])
    row["n_videos"] = len(row.get("videos") or [])
    return row


def parse_label_ref(ref: str) -> int | None:
    ref = ref.strip()
    if ref.isdigit():
        return int(ref)
    if m := re.search(r"label/(\d+)", ref):
        return int(m.group(1))
    if m := re.fullmatch(r"\[?l(\d+)\]?", ref, re.I):  # Discogs shorthand like [l12345]
        return int(m.group(1))
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = DB(DB_PATH)
    if not db.has_labels() and LEGACY_DATA.is_dir():
        print("First start: importing legacy Data/ folder ...")
        import_legacy(db, LEGACY_DATA)
    api = Discogs(DISCOGS_TOKEN)
    syncer = Syncer(api, db)
    syncer.start()
    app.state.db, app.state.api, app.state.syncer = db, api, syncer
    yield
    await syncer.stop()
    await api.close()


app = FastAPI(title="Power Digger 3000", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/me")
async def me():
    db: DB = app.state.db
    if not DISCOGS_TOKEN:
        return {"username": None, "token": False, "currency": CURRENCY}
    if (cached := db.get_kv("identity")) is None:
        try:
            cached = await app.state.api.identity()
            db.set_kv("identity", cached)
        except DiscogsError:
            return {"username": None, "token": False, "currency": CURRENCY}
    return {"username": cached["username"], "token": True, "currency": CURRENCY}


@app.get("/api/labels")
async def labels():
    return app.state.db.list_labels()


@app.get("/api/search/labels")
async def search_labels(q: str):
    if label_id := parse_label_ref(q):
        return [{"id": label_id, "title": f"Label #{label_id}", "thumb": None}]
    data = await app.state.api.search_labels(q)
    return [{"id": r["id"], "title": r["title"], "thumb": r.get("thumb")} for r in data.get("results", [])]


class AddLabel(BaseModel):
    ref: str
    vinyl_only: bool = True
    prices: bool = False


@app.post("/api/labels")
async def add_label(body: AddLabel):
    label_id = parse_label_ref(body.ref)
    if label_id is None:
        raise HTTPException(400, "Couldn't find a label id. Paste a discogs.com/label/... link or pick from search.")
    job = app.state.syncer.enqueue(label_id, vinyl_only=body.vinyl_only, prices=body.prices)
    return job.public()


@app.delete("/api/labels/{label_id}")
async def delete_label(label_id: int):
    app.state.syncer.cancel(label_id)
    app.state.db.delete_label(label_id)
    return {"ok": True}


@app.get("/api/labels/{label_id}")
async def label_detail(label_id: int):
    db: DB = app.state.db
    label = db.get_label(label_id)
    if not label:
        raise HTTPException(404, "Label not in database")
    rows = [_decode(r) for r in db.label_releases(label_id)]
    # Score vinyl and other formats separately so cheap digital/CD rows don't skew the percentiles.
    rows = score_releases([r for r in rows if r["is_vinyl"]]) + score_releases([r for r in rows if not r["is_vinyl"]])
    label["summary"] = label_summary(rows)
    label["releases"] = [{k: r.get(k) for k in LIST_FIELDS} for r in rows]
    return label


@app.get("/api/releases/{release_id}")
async def release(release_id: int, refresh: bool = False):
    db: DB = app.state.db
    row = db.get_release(release_id)
    if row is None or row["detail_at"] is None or refresh:
        # On-demand enrichment: shares the rate limiter with the background sync.
        await app.state.syncer.fetch_detail(release_id)
        row = db.get_release(release_id)
    if row is None:
        raise HTTPException(404, "Release not found")
    return _decode(row)


@app.put("/api/wants/{release_id}")
async def add_want(release_id: int):
    user = await me()
    if not user["username"]:
        raise HTTPException(401, "No Discogs token configured")
    await app.state.api.add_want(user["username"], release_id)
    app.state.db.set_user_want(release_id, True)
    return {"user_want": 1}


@app.delete("/api/wants/{release_id}")
async def remove_want(release_id: int):
    user = await me()
    if not user["username"]:
        raise HTTPException(401, "No Discogs token configured")
    await app.state.api.remove_want(user["username"], release_id)
    app.state.db.set_user_want(release_id, False)
    return {"user_want": 0}


@app.get("/api/jobs")
async def jobs():
    syncer: Syncer = app.state.syncer
    return {
        "jobs": [{**j.public(), "eta_min": eta_minutes(j)} for j in syncer.jobs.values()],
        "rate_remaining": syncer.api.remaining,
    }


@app.post("/api/jobs/{label_id}/cancel")
async def cancel_job(label_id: int):
    app.state.syncer.cancel(label_id)
    return {"ok": True}


@app.exception_handler(DiscogsError)
async def discogs_error(_, exc: DiscogsError):
    return JSONResponse({"detail": str(exc)}, status_code=502 if exc.status in (0, 429) or exc.status >= 500 else exc.status)
