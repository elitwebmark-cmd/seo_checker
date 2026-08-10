# -*- coding: utf-8 -*-
"""Google Ads API — Keyword Planner по домену (безкоштовно).
Вхід: домен -> GenerateKeywordIdeas (UrlSeed, гео Україна) ->
топ-N комерційних запитів + сумарний помісячний тренд обсягів (12 міс).
REST, самооновлення access-token через refresh_token. Кеш по домену.
Повертає None, якщо ключів нема / помилка -> у звіті блок просто ховається."""
from __future__ import annotations
import time
import requests
import config

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CACHE = {}
_TOKEN = {"value": None, "exp": 0}

_MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def _ready() -> bool:
    return all([
        config.GOOGLE_ADS_DEVELOPER_TOKEN, config.GOOGLE_ADS_CLIENT_ID,
        config.GOOGLE_ADS_CLIENT_SECRET, config.GOOGLE_ADS_REFRESH_TOKEN,
        config.GOOGLE_ADS_CUSTOMER_ID,
    ])


def _access_token() -> str:
    now = time.time()
    if _TOKEN["value"] and now < _TOKEN["exp"]:
        return _TOKEN["value"]
    r = requests.post(_TOKEN_URL, data={
        "client_id": config.GOOGLE_ADS_CLIENT_ID,
        "client_secret": config.GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": config.GOOGLE_ADS_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=config.KWPLAN_TIMEOUT)
    r.raise_for_status()
    j = r.json()
    _TOKEN["value"] = j["access_token"]
    _TOKEN["exp"] = now + int(j.get("expires_in", 3600)) - 60
    return _TOKEN["value"]


def _cached(key, producer):
    ttl = getattr(config, "SEMRUSH_CACHE_TTL", 604800)
    now = time.time()
    hit = _CACHE.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    val = producer()
    _CACHE[key] = (now, val)
    return val


def _is_commercial(kw: str) -> bool:
    k = (kw or "").lower()
    return any(p in k for p in config.COMMERCIAL_PATTERNS)


def _clean_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "").strip("/")
    return d.split("/")[0]


def keyword_ideas(domain: str) -> dict:
    if not _ready():
        return None
    return _cached(f"kwplan:{domain}", lambda: _fetch(domain))


def _fetch(domain: str) -> dict:
    cid = config.GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
    url = (f"https://googleads.googleapis.com/{config.GOOGLE_ADS_API_VERSION}"
           f"/customers/{cid}:generateKeywordIdeas")
    headers = {
        "developer-token": config.GOOGLE_ADS_DEVELOPER_TOKEN,
        "Authorization": f"Bearer {_access_token()}",
        "content-type": "application/json",
    }
    if config.GOOGLE_ADS_LOGIN_CUSTOMER_ID:
        headers["login-customer-id"] = config.GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace("-", "")
    body = {
        "geoTargetConstants": [f"geoTargetConstants/{config.KWPLAN_GEO}"],
        "language": f"languageConstants/{config.KWPLAN_LANG}",
        "keywordPlanNetwork": "GOOGLE_SEARCH",
        "urlSeed": {"url": _clean_domain(domain)},
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=config.KWPLAN_TIMEOUT)
        if r.status_code >= 400:
            return None
        rows = r.json().get("results", []) or []
    except Exception:
        return None
    if not rows:
        return None

    kws = []
    trend_acc = {}   # (year, month) -> сума обсягів
    for row in rows:
        kw = row.get("text")
        m = row.get("keywordIdeaMetrics") or {}
        vol = int(m.get("avgMonthlySearches") or 0)
        micros = m.get("highTopOfPageBidMicros") or m.get("lowTopOfPageBidMicros") or 0
        cpc = round(int(micros) / 1_000_000, 2) if micros else None   # грн (акаунт у грн)
        comp = m.get("competition")   # LOW/MEDIUM/HIGH
        monthly = m.get("monthlySearchVolumes") or []
        if kw:
            kws.append({"keyword": kw, "volume": vol, "cpc": cpc,
                        "competition": comp, "commercial": _is_commercial(kw)})
        for mv in monthly:
            y = int(mv.get("year") or 0)
            mo = _MONTHS.get(mv.get("month"), 0)
            if y and mo:
                trend_acc[(y, mo)] = trend_acc.get((y, mo), 0) + int(mv.get("monthlySearches") or 0)

    # топ комерційних (fallback на всі), відсортовані за обсягом
    comm = [k for k in kws if k["commercial"]]
    top = sorted(comm or kws, key=lambda x: -x["volume"])[:config.KWPLAN_LIMIT]

    # сумарний тренд за останні 12 точок
    trend_points, trend_labels = [], []
    for (y, mo) in sorted(trend_acc.keys())[-12:]:
        trend_points.append(trend_acc[(y, mo)])
        trend_labels.append(f"{mo:02d}.{str(y)[2:]}")

    change_pct = None
    if len(trend_points) >= 2 and trend_points[0]:
        change_pct = round((trend_points[-1] - trend_points[0]) / trend_points[0] * 100)

    return {
        "keywords": top,
        "total_ideas": len(kws),
        "trend": trend_points,
        "trend_labels": trend_labels,
        "change_pct": change_pct,
        "source": "Google Keyword Planner",
    }


def debug(domain: str) -> dict:
    """Сира діагностика: чи готові ключі, чи проходить токен, що повертає API."""
    cid = config.GOOGLE_ADS_CLIENT_ID or ""
    rt = config.GOOGLE_ADS_REFRESH_TOKEN or ""
    out = {"ready": _ready(), "customer_id": bool(config.GOOGLE_ADS_CUSTOMER_ID),
           "login_customer_id": bool(config.GOOGLE_ADS_LOGIN_CUSTOMER_ID),
           "client_id_tail": cid[-30:] if cid else None,
           "client_secret_len": len(config.GOOGLE_ADS_CLIENT_SECRET or ""),
           "refresh_token_prefix": rt[:12] if rt else None}
    if not _ready():
        out["error"] = "не всі ключі задані (developer_token/client_id/secret/refresh_token/customer_id)"
        return out
    try:
        tr = requests.post(_TOKEN_URL, data={
            "client_id": config.GOOGLE_ADS_CLIENT_ID,
            "client_secret": config.GOOGLE_ADS_CLIENT_SECRET,
            "refresh_token": config.GOOGLE_ADS_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }, timeout=config.KWPLAN_TIMEOUT)
        if tr.status_code >= 400:
            out["access_token_error"] = {"status": tr.status_code, "body": tr.json()}
            return out
        out["access_token"] = "OK"
    except Exception as e:
        out["access_token_error"] = str(e)[:400]
        return out

    # які акаунти взагалі доступні цьому токену
    try:
        rr = requests.get(
            f"https://googleads.googleapis.com/{config.GOOGLE_ADS_API_VERSION}"
            f"/customers:listAccessibleCustomers",
            headers={"developer-token": config.GOOGLE_ADS_DEVELOPER_TOKEN,
                     "Authorization": f"Bearer {_access_token()}"},
            timeout=config.KWPLAN_TIMEOUT)
        out["accessible_customers"] = rr.json()
    except Exception as e:
        out["accessible_customers_error"] = str(e)[:400]
    cid = config.GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
    url = (f"https://googleads.googleapis.com/{config.GOOGLE_ADS_API_VERSION}"
           f"/customers/{cid}:generateKeywordIdeas")
    headers = {"developer-token": config.GOOGLE_ADS_DEVELOPER_TOKEN,
               "Authorization": f"Bearer {_access_token()}",
               "content-type": "application/json"}
    if config.GOOGLE_ADS_LOGIN_CUSTOMER_ID:
        headers["login-customer-id"] = config.GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace("-", "")
    body = {"geoTargetConstants": [f"geoTargetConstants/{config.KWPLAN_GEO}"],
            "language": f"languageConstants/{config.KWPLAN_LANG}",
            "keywordPlanNetwork": "GOOGLE_SEARCH",
            "urlSeed": {"url": _clean_domain(domain)}}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=config.KWPLAN_TIMEOUT)
        out["http_status"] = r.status_code
        j = r.json()
        if r.status_code >= 400:
            out["api_error"] = j
            return out
        rows = j.get("results", []) or []
        out["results_count"] = len(rows)
        out["sample"] = rows[:3]
    except Exception as e:
        out["request_error"] = str(e)[:400]
    return out
