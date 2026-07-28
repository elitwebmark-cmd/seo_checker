# -*- coding: utf-8 -*-
"""Google Trends по ніші через SerpApi (data_type=TIMESERIES).
Апроксимований тренд попиту: середнє по кількох комерційних запитах (індекс 0..100)
за останні 12 місяців, гео — Україна. Один платний запит SerpApi."""
from __future__ import annotations
import requests
import config

SERPAPI_URL = "https://serpapi.com/search"


def niche_trend(keywords, geo: str = "UA", date: str = "today 12-m") -> dict:
    kws = [str(k).strip() for k in (keywords or []) if k and str(k).strip()][:5]
    if not config.SERPAPI_KEY or not kws:
        return None
    params = {
        "engine": "google_trends",
        "q": ",".join(kws),
        "geo": geo,
        "date": date,
        "data_type": "TIMESERIES",
        "api_key": config.SERPAPI_KEY,
    }
    try:
        d = requests.get(SERPAPI_URL, params=params, timeout=config.ADS_TIMEOUT).json()
    except Exception:
        return None
    if d.get("error"):
        return None
    timeline = ((d.get("interest_over_time") or {}).get("timeline_data")) or []
    points = []
    for e in timeline:
        nums = []
        for v in (e.get("values") or []):
            ev = v.get("extracted_value")
            if ev is None:
                try:
                    ev = float(v.get("value"))
                except (TypeError, ValueError):
                    ev = None
            if ev is not None:
                nums.append(float(ev))
        if not nums:
            continue
        points.append({"value": round(sum(nums) / len(nums), 1),
                       "ts": e.get("timestamp"), "label": e.get("date", "")})
    if len(points) < 3:
        return None
    n = len(points)
    seg = max(1, n // 6)
    head = sum(p["value"] for p in points[:seg]) / seg
    tail = sum(p["value"] for p in points[-seg:]) / seg
    change = round((tail - head) / head * 100) if head > 0 else None
    return {
        "points": points,
        "keywords": kws,
        "geo": geo,
        "change_pct": change,
        "avg": round(sum(p["value"] for p in points) / n, 1),
        "peak": max(p["value"] for p in points),
    }
