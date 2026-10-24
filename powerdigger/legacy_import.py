"""Import the pre-2.0 Data/<Label>/raw_*.json dumps into SQLite."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .db import DB


def import_legacy(db: DB, data_dir: Path, log=print) -> int:
    if not data_dir.is_dir():
        return 0
    imported = 0
    for folder in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        files = [folder / f"raw_{k}.json" for k in ("releases", "prices", "stats")]
        if not files[0].exists():
            continue
        releases = json.loads(files[0].read_text())
        prices = json.loads(files[1].read_text()) if files[1].exists() else [None] * len(releases)
        stats = json.loads(files[2].read_text()) if files[2].exists() else [None] * len(releases)
        if not releases:
            continue

        # Folder names are label names with spaces removed; find the matching label id.
        candidates = Counter(
            (lbl["id"], lbl["name"])
            for r in releases for lbl in r.get("labels") or []
            if lbl.get("name", "").replace(" ", "") == folder.name
        )
        if not candidates:
            candidates = Counter((lbl["id"], lbl["name"]) for r in releases for lbl in (r.get("labels") or [])[:1])
        (label_id, label_name), _ = candidates.most_common(1)[0]

        if db.get_label(label_id) is None:
            db.upsert_label({"id": label_id, "name": label_name})
        fetched_at = datetime.fromtimestamp(files[0].stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        for r, p, s in zip(releases, prices, stats):
            r = dict(r)
            if s:
                lp = s.get("lowest_price")
                r["lowest_price"] = lp.get("value") if lp else None
                r["_currency"] = lp.get("currency") if lp else None
                r["num_for_sale"] = s.get("num_for_sale")
            db.upsert_detail(r, p or None, fetched_at=fetched_at)
            catno = next((lbl.get("catno") for lbl in r.get("labels") or [] if lbl["id"] == label_id), None)
            db.conn.execute(
                "INSERT OR IGNORE INTO label_releases (label_id, release_id, catno) VALUES (?, ?, ?)",
                (label_id, r["id"], catno),
            )
        db.commit()
        imported += 1
        log(f"  imported {label_name} ({len(releases)} releases)")
    return imported
