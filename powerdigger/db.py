"""SQLite storage. One connection, used from the asyncio loop thread only."""
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    profile TEXT,
    image TEXT,
    parent TEXT,        -- json {id, name}
    sublabels TEXT,     -- json [{id, name}]
    catalog_synced_at TEXT,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY,
    title TEXT, artist TEXT, year INTEGER, thumb TEXT, format TEXT,
    is_vinyl INTEGER,
    want INTEGER, have INTEGER,
    user_want INTEGER DEFAULT 0, user_have INTEGER DEFAULT 0,
    -- filled by the per-release detail call
    detail_at TEXT,
    country TEXT, genres TEXT, styles TEXT, released TEXT,
    rating_avg REAL, rating_count INTEGER,
    lowest_price REAL, num_for_sale INTEGER, currency TEXT,
    master_id INTEGER, image TEXT,
    videos TEXT, tracklist TEXT, notes TEXT, formats TEXT,
    price_suggestions TEXT
);
CREATE TABLE IF NOT EXISTS label_releases (
    label_id INTEGER NOT NULL,
    release_id INTEGER NOT NULL,
    catno TEXT,
    PRIMARY KEY (label_id, release_id)
);
CREATE INDEX IF NOT EXISTS idx_lr_release ON label_releases(release_id);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""

VINYL_RE = re.compile(r'(\d+(\.\d+)?"|\bLP\b|Vinyl|Flexi|Lathe|Acetate)', re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def commit(self):
        self.conn.commit()

    # --- kv ------------------------------------------------------------------

    def get_kv(self, key):
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else None

    def set_kv(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))
        self.commit()

    # --- labels --------------------------------------------------------------

    def upsert_label(self, data: dict):
        images = data.get("images") or []
        image = next((i["uri"] for i in images if i.get("type") == "primary"), None) or (images[0]["uri"] if images else None)
        parent = data.get("parent_label")
        subs = [{"id": s["id"], "name": s["name"]} for s in data.get("sublabels") or []]
        self.conn.execute(
            """INSERT INTO labels (id, name, profile, image, parent, sublabels, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, profile=excluded.profile,
                 image=excluded.image, parent=excluded.parent, sublabels=excluded.sublabels""",
            (data["id"], data["name"], data.get("profile"), image,
             json.dumps({"id": parent["id"], "name": parent["name"]}) if parent else None,
             json.dumps(subs), now_iso()),
        )
        self.commit()

    def mark_catalog_synced(self, label_id: int):
        self.conn.execute("UPDATE labels SET catalog_synced_at=? WHERE id=?", (now_iso(), label_id))
        self.commit()

    def delete_label(self, label_id: int):
        self.conn.execute("DELETE FROM label_releases WHERE label_id=?", (label_id,))
        self.conn.execute("DELETE FROM labels WHERE id=?", (label_id,))
        # Drop releases that no other label references.
        self.conn.execute("DELETE FROM releases WHERE id NOT IN (SELECT release_id FROM label_releases)")
        self.commit()

    def list_labels(self):
        rows = self.conn.execute(
            """SELECT l.id, l.name, l.image, l.catalog_synced_at,
                      COUNT(r.id) AS n_releases,
                      SUM(r.detail_at IS NOT NULL) AS n_detailed,
                      SUM(r.is_vinyl) AS n_vinyl
               FROM labels l
               LEFT JOIN label_releases lr ON lr.label_id = l.id
               LEFT JOIN releases r ON r.id = lr.release_id
               GROUP BY l.id ORDER BY l.name COLLATE NOCASE"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_label(self, label_id: int):
        row = self.conn.execute("SELECT * FROM labels WHERE id=?", (label_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["parent"] = json.loads(d["parent"]) if d["parent"] else None
        d["sublabels"] = json.loads(d["sublabels"]) if d["sublabels"] else []
        return d

    # --- releases ------------------------------------------------------------

    def upsert_listing(self, label_id: int, items: list[dict]):
        """Store items from /labels/{id}/releases."""
        for it in items:
            stats = it.get("stats") or {}
            comm = stats.get("community") or {}
            user = stats.get("user") or {}
            fmt = it.get("format") or ""
            self.conn.execute(
                """INSERT INTO releases (id, title, artist, year, thumb, format, is_vinyl, want, have, user_want, user_have)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, artist=excluded.artist,
                     year=excluded.year, thumb=COALESCE(excluded.thumb, thumb), format=excluded.format,
                     is_vinyl=CASE WHEN detail_at IS NULL THEN excluded.is_vinyl ELSE is_vinyl END,
                     want=excluded.want, have=excluded.have,
                     user_want=excluded.user_want, user_have=excluded.user_have""",
                (it["id"], it.get("title"), it.get("artist"), it.get("year") or None, it.get("thumb") or None,
                 fmt, int(bool(VINYL_RE.search(fmt))), comm.get("in_wantlist"), comm.get("in_collection"),
                 int(bool(user.get("in_wantlist"))), int(bool(user.get("in_collection")))),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO label_releases (label_id, release_id, catno) VALUES (?, ?, ?)",
                (label_id, it["id"], it.get("catno")),
            )
        self.commit()

    def upsert_detail(self, r: dict, prices: dict | None = None, fetched_at: str | None = None):
        """Store a full /releases/{id} payload."""
        comm = r.get("community") or {}
        rating = comm.get("rating") or {}
        formats = r.get("formats") or []
        images = r.get("images") or []
        image = next((i["uri"] for i in images if i.get("type") == "primary"), None) or (images[0]["uri"] if images else None)
        artist = r.get("artists_sort") or ", ".join(a["name"] for a in r.get("artists") or [])
        videos = [
            {"uri": v["uri"], "title": v.get("title"), "duration": v.get("duration")}
            for v in r.get("videos") or [] if "youtube.com" in v.get("uri", "") or "youtu.be" in v.get("uri", "")
        ]
        tracklist = [
            {"position": t.get("position"), "title": t.get("title"), "duration": t.get("duration")}
            for t in r.get("tracklist") or [] if t.get("type_", "track") == "track"
        ]
        fmt_desc = []
        for f in formats:
            fmt_desc.extend([f.get("name", "")] + (f.get("descriptions") or []) + ([f["text"]] if f.get("text") else []))
        lowest = r.get("lowest_price")
        if isinstance(lowest, dict):  # legacy marketplace/stats shape
            lowest = lowest.get("value")
        fmt_str = ", ".join(d for d in fmt_desc if d and d != "Vinyl")
        values = dict(
            title=r.get("title"), artist=artist, year=r.get("year") or None, format=fmt_str,
            thumb=r.get("thumb") or None, is_vinyl=int(any(f.get("name") == "Vinyl" for f in formats)),
            want=comm.get("want"), have=comm.get("have"),
            detail_at=fetched_at or now_iso(), country=r.get("country"),
            genres=json.dumps(r.get("genres") or []), styles=json.dumps(r.get("styles") or []),
            released=r.get("released"), rating_avg=rating.get("average"), rating_count=rating.get("count"),
            lowest_price=lowest, num_for_sale=r.get("num_for_sale"), currency=r.get("_currency"),
            master_id=r.get("master_id"), image=image, videos=json.dumps(videos),
            tracklist=json.dumps(tracklist), notes=r.get("notes"), formats=json.dumps(fmt_desc),
        )
        if prices is not None:
            values["price_suggestions"] = json.dumps(
                {k: round(v["value"], 2) for k, v in prices.items() if isinstance(v, dict) and "value" in v}
            )
        cols = ", ".join(values)
        updates = ", ".join(f"{k}=excluded.{k}" for k in values if k not in ("thumb", "format"))
        updates += ", thumb=COALESCE(excluded.thumb, thumb), format=COALESCE(format, excluded.format)"
        self.conn.execute(
            f"INSERT INTO releases (id, {cols}) VALUES (?, {', '.join('?' * len(values))}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            (r["id"], *values.values()),
        )
        self.commit()

    def set_user_want(self, release_id: int, value: bool):
        self.conn.execute("UPDATE releases SET user_want=? WHERE id=?", (int(value), release_id))
        self.commit()

    def releases_needing_detail(self, label_id: int, vinyl_only: bool, max_age_days: int):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat(timespec="seconds")
        # Most promising first (smoothed want/have), so the interesting stuff is ready early.
        rows = self.conn.execute(
            f"""SELECT r.id FROM releases r JOIN label_releases lr ON lr.release_id = r.id
                WHERE lr.label_id = ? AND (r.detail_at IS NULL OR r.detail_at < ?)
                {"AND r.is_vinyl = 1" if vinyl_only else ""}
                ORDER BY (COALESCE(r.want, 0) + 2.0) / (COALESCE(r.have, 0) + 10.0) DESC""",
            (label_id, cutoff),
        ).fetchall()
        return [r["id"] for r in rows]

    def label_releases(self, label_id: int):
        rows = self.conn.execute(
            """SELECT r.*, lr.catno FROM releases r JOIN label_releases lr ON lr.release_id = r.id
               WHERE lr.label_id = ?""",
            (label_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_release(self, release_id: int):
        row = self.conn.execute(
            """SELECT r.*, (SELECT GROUP_CONCAT(l.name || ' – ' || COALESCE(lr.catno, ''), ' · ')
                            FROM label_releases lr JOIN labels l ON l.id = lr.label_id
                            WHERE lr.release_id = r.id) AS label_info
               FROM releases r WHERE r.id = ?""",
            (release_id,),
        ).fetchone()
        return dict(row) if row else None

    def has_labels(self) -> bool:
        return self.conn.execute("SELECT 1 FROM labels LIMIT 1").fetchone() is not None
