"""Клієнт SemRush Analytics API (v3, api.semrush.com).
Використовує ключ SEMRUSH_API_KEY. База за замовч. — google.com.ua (ua)."""
from __future__ import annotations
import requests
from typing import List, Dict, Any
import config


class SemrushError(Exception):
    pass


def _db(db):
    return db or config.SEMRUSH_DB


def _request(params: Dict[str, Any]) -> str:
    params = dict(params)
    params["key"] = config.SEMRUSH_API_KEY
    r = requests.get(config.SEMRUSH_BASE, params=params, timeout=config.HTTP_TIMEOUT)
    text = r.text.strip()
    if r.status_code != 200:
        raise SemrushError(f"HTTP {r.status_code}: {text[:200]}")
    if text.startswith("ERROR"):
        if "NOTHING FOUND" in text.upper():
            return ""
        raise SemrushError(text)
    return text


def _parse_csv(text: str) -> List[Dict[str, str]]:
    if not text:
        return []
    lines = text.splitlines()
    header = lines[0].split(";")
    out = []
    for line in lines[1:]:
        cells = line.split(";")
        if len(cells) != len(header):
            continue
        out.append(dict(zip(header, cells)))
    return out


def domain_overview(domain: str, db: str = None) -> Dict[str, Any]:
    # Ad/At/Ac — платні (AdWords) ключі, трафік і приблизний місячний бюджет
    text = _request({
        "type": "domain_ranks",
        "domain": domain,
        "database": _db(db),
        "export_columns": "Dn,Rk,Or,Ot,Oc,Ad,At,Ac",
    })
    rows = _parse_csv(text)
    if not rows:
        return {"organic_keywords": 0, "organic_traffic": 0, "rank": None,
                "adwords_keywords": 0, "adwords_traffic": 0, "adwords_cost": 0}
    row = rows[0]
    def _int(*keys):
        for k in keys:
            if k in row:
                try:
                    return int(float(row.get(k) or 0))
                except (ValueError, TypeError):
                    return 0
        return 0
    return {
        "organic_keywords": _int("Organic Keywords"),
        "organic_traffic": _int("Organic Traffic"),
        "rank": row.get("Rank"),
        "adwords_keywords": _int("Adwords Keywords"),
        "adwords_traffic": _int("Adwords Traffic"),
        "adwords_cost": _int("Adwords Cost", "Adwords Traffic Cost", "Adwords Budget"),
    }


def domain_history(domain: str, db: str = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Історія по місяцях: орг. ключі/трафік + платні ключі/трафік/бюджет."""
    try:
        text = _request({
            "type": "domain_rank_history",
            "domain": domain,
            "database": _db(db),
            "export_columns": "Rk,Or,Ot,Oc,Ad,At,Ac,Dt",
            "display_limit": max(1, int(limit)),
            "display_sort": "dt_desc",
        })
    except SemrushError:
        return []
    out = []
    for row in _parse_csv(text):
        out.append({
            "date": (row.get("Date", "") or "")[:6],   # YYYYMM
            "org_kw": _safe_int(row.get("Organic Keywords")),
            "org_traffic": _safe_int(row.get("Organic Traffic")),
            "ad_kw": _safe_int(row.get("Adwords Keywords")),
            "ad_traffic": _safe_int(row.get("Adwords Traffic")),
            "ad_cost": _safe_int(row.get("Adwords Cost")),
        })
    return out


def _ctr(pos: int) -> float:
    return config.CTR_BY_POS.get(int(pos or 99), config.CTR_FLOOR)


def top_pages(domain: str, db: str = None, limit: int = 10,
              kw_scan: int = 500) -> List[Dict[str, Any]]:
    """ТОП сторінок за трафіком. Рахуємо з найтрафікованіших орг. запитів
    (обсяг × CTR позиції) і агрегуємо по URL — надійніше за колонку traffic."""
    try:
        text = _request({
            "type": "domain_organic",
            "domain": domain,
            "database": _db(db),
            "display_limit": max(1, int(kw_scan)),
            "display_sort": "tr_desc",
            "export_columns": "Ph,Po,Nq,Ur",
        })
    except SemrushError:
        return []
    agg = {}
    for row in _parse_csv(text):
        url = row.get("Url") or row.get("URL") or ""
        if not url:
            continue
        pos = _safe_int(row.get("Position"))
        vol = _safe_int(row.get("Search Volume"))
        a = agg.setdefault(url, {"url": url, "keywords": 0, "traffic": 0.0})
        a["keywords"] += 1
        a["traffic"] += vol * _ctr(pos)
    pages = sorted(agg.values(), key=lambda x: x["traffic"], reverse=True)[:limit]
    for p in pages:
        p["traffic"] = int(round(p["traffic"]))
    return pages


def organic_keywords(domain: str, pos_min: int, pos_max: int,
                     limit: int = 2000, db: str = None) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    dfilter = f"+|Po|Gt|{pos_min - 1}|+|Po|Lt|{pos_max + 1}"
    text = _request({
        "type": "domain_organic",
        "domain": domain,
        "database": _db(db),
        "display_limit": max(1, int(limit)),
        "display_sort": "nq_desc",
        "display_filter": dfilter,
        "export_columns": "Ph,Po,Nq,Cp,Co,Kd,In,Ur",
    })
    for row in _parse_csv(text):
        collected.append({
            "keyword": row.get("Keyword", ""),
            "position": _safe_int(row.get("Position")),
            "volume": _safe_int(row.get("Search Volume")),
            "cpc": _safe_float(row.get("CPC")),
            "competition": _safe_float(row.get("Competition")),
            "kd": _safe_float(row.get("Keyword Difficulty")),
            "intent": (row.get("Intents", "") or "").split(",")[0].strip(),
            "url": row.get("Url", ""),
        })
    return collected


def _safe_int(v):
    try:
        return int(float(v or 0))
    except (ValueError, TypeError):
        return 0


def _safe_float(v):
    try:
        return float(v or 0)
    except (ValueError, TypeError):
        return 0.0
