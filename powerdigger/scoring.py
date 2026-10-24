"""Digger metrics. All scores are relative to the label's own catalogue.

- ratio:  smoothed want/have. (want+2)/(have+10) pulls tiny samples toward ~0.2,
          so a 3-want/1-have release doesn't outrank a 400/300 classic.
- rating: Bayesian average, shrunk toward the label's mean with 5 phantom votes.
- dig:    0-100 blend of percentile ranks: scarcity (ratio) 50%, demand (log want)
          25%, quality (rating) 25%. Without a rating the other two are renormalised.
Tags:
- sleeper:  top-20% ratio but below-median "have" - obscure records people hunt for.
- hot:      top-10% wantlist count on the label.
- bargain:  dig >= 60 and the cheapest copy is at or below the label's median price,
            or below 70% of Discogs' VG+ suggestion when price suggestions exist.
- acclaimed: Bayesian rating >= 4.5 with at least 10 votes.
"""
import math
from statistics import median


def _pct_ranks(values: list[float | None]) -> list[float | None]:
    present = sorted(v for v in values if v is not None)
    n = len(present)
    if n == 0:
        return [None] * len(values)
    if n == 1:
        return [0.5 if v is not None else None for v in values]
    # Average rank for ties, normalised to 0..1.
    first, last = {}, {}
    for i, v in enumerate(present):
        first.setdefault(v, i)
        last[v] = i
    return [None if v is None else (first[v] + last[v]) / 2 / (n - 1) for v in values]


def score_releases(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    for r in rows:
        want, have = r.get("want") or 0, r.get("have") or 0
        r["ratio"] = (want + 2) / (have + 10)
        r["raw_ratio"] = want / have if have else None

    rated = [r for r in rows if r.get("rating_count")]
    mean_rating = (
        sum(r["rating_avg"] * r["rating_count"] for r in rated) / sum(r["rating_count"] for r in rated)
        if rated else 3.8
    )
    for r in rows:
        c = r.get("rating_count") or 0
        r["rating_bayes"] = (r["rating_avg"] * c + mean_rating * 5) / (c + 5) if c else None

    pr_ratio = _pct_ranks([r["ratio"] for r in rows])
    pr_want = _pct_ranks([math.log1p(r.get("want") or 0) for r in rows])
    pr_rating = _pct_ranks([r["rating_bayes"] for r in rows])

    haves = [r.get("have") or 0 for r in rows]
    med_have = median(haves)
    prices = [r["lowest_price"] for r in rows if r.get("lowest_price")]
    med_price = median(prices) if prices else None

    for r, a, b, c in zip(rows, pr_ratio, pr_want, pr_rating):
        if c is None:
            dig = (0.5 * a + 0.25 * b) / 0.75
        else:
            dig = 0.5 * a + 0.25 * b + 0.25 * c
        r["dig"] = round(dig * 100)
        tags = []
        if a >= 0.8 and (r.get("have") or 0) <= med_have and (r.get("want") or 0) >= 5:
            tags.append("sleeper")
        if b >= 0.9 and (r.get("want") or 0) >= 20:
            tags.append("hot")
        if r["rating_bayes"] and r["rating_bayes"] >= 4.5 and (r.get("rating_count") or 0) >= 10:
            tags.append("acclaimed")
        lp = r.get("lowest_price")
        if lp and r.get("num_for_sale"):
            sugg = (r.get("price_suggestions") or {}).get("Very Good Plus (VG+)")
            if sugg and lp < 0.7 * sugg:
                tags.append("bargain")
            elif not sugg and r["dig"] >= 60 and med_price and lp <= med_price:
                tags.append("bargain")
        r["tags"] = tags
    return rows


def label_summary(rows: list[dict]) -> dict:
    styles: dict[str, int] = {}
    years: dict[int, int] = {}
    for r in rows:
        for s in r.get("styles") or []:
            styles[s] = styles.get(s, 0) + 1
        if r.get("year"):
            years[r["year"]] = years.get(r["year"], 0) + 1
    prices = [r["lowest_price"] for r in rows if r.get("lowest_price")]
    ratios = [r["raw_ratio"] for r in rows if r.get("raw_ratio") is not None]
    return {
        "styles": sorted(styles.items(), key=lambda kv: -kv[1])[:24],
        "years": sorted(years.items()),
        "median_price": round(median(prices), 2) if prices else None,
        "median_ratio": round(median(ratios), 2) if ratios else None,
        "for_sale": sum(1 for r in rows if r.get("num_for_sale")),
    }
