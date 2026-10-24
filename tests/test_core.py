from powerdigger.db import DB
from powerdigger.scoring import score_releases
from powerdigger.server import parse_label_ref


def test_parse_label_ref():
    assert parse_label_ref("https://www.discogs.com/label/255-Basic-Channel") == 255
    assert parse_label_ref("https://www.discogs.com/de/label/8264") == 8264
    assert parse_label_ref(" 1234 ") == 1234
    assert parse_label_ref("[l42]") == 42
    assert parse_label_ref("Tresor") is None


def test_scoring_prefers_scarce_and_wanted():
    rows = [
        {"id": 1, "want": 900, "have": 150, "rating_avg": 4.8, "rating_count": 60},  # wanted & scarce
        {"id": 2, "want": 900, "have": 2000, "rating_avg": 4.2, "rating_count": 80},  # common classic
        {"id": 3, "want": 3, "have": 1},  # tiny sample must not win
        {"id": 4, "want": 10, "have": 200},
    ]
    scored = {r["id"]: r for r in score_releases(rows)}
    assert scored[1]["dig"] == max(r["dig"] for r in rows)
    assert scored[3]["dig"] < scored[1]["dig"]
    assert "acclaimed" in scored[1]["tags"]


def test_listing_then_detail_roundtrip(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert_label({"id": 7, "name": "Test", "sublabels": [{"id": 8, "name": "Sub"}]})
    db.upsert_listing(7, [
        {"id": 100, "title": "A", "artist": "X", "year": 1995, "format": '12", Promo', "catno": "T01",
         "thumb": "t.jpg", "stats": {"community": {"in_wantlist": 50, "in_collection": 10}, "user": {"in_wantlist": 1}}},
        {"id": 101, "title": "B", "artist": "Y", "format": "File, MP3", "catno": "T02D", "stats": {}},
    ])
    assert db.releases_needing_detail(7, vinyl_only=True, max_age_days=30) == [100]
    db.upsert_detail({"id": 100, "title": "A", "formats": [{"name": "Vinyl", "descriptions": ['12"']}],
                      "community": {"want": 55, "have": 11, "rating": {"average": 4.5, "count": 3}},
                      "lowest_price": 12.5, "num_for_sale": 2,
                      "videos": [{"uri": "https://www.youtube.com/watch?v=abcdefghijk", "title": "v"}]})
    r = db.get_release(100)
    assert (r["want"], r["user_want"], r["thumb"], r["format"]) == (55, 1, "t.jpg", '12", Promo')
    assert db.releases_needing_detail(7, vinyl_only=True, max_age_days=30) == []
    db.delete_label(7)
    assert db.get_release(100) is None
