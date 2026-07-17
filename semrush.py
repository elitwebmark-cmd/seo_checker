"""Клієнт SemRush Analytics API (офіційний, api.semrush.com).
Використовує ключ SEMRUSH_API_KEY. База — google.com.ua (SEMRUSH_DB=ua).
Документація типів звітів: domain_ranks, domain_organic.
"""
from __future__ import annotations
import requests
from typing import List, Dict, Any
import config


class SemrushError(Exception):
    pass


def _request(params: Dict[str, Any]) -> str:
    params = dict(params)
    params["key"] = config.SEMRUSH_API_KEY
    r = requests.get(config.SEMRUSH_BASE, params=params, timeout=config.HTTP_TIMEOUT)
    text = r.text.strip()
    if r.status_code != 200:
        raise SemrushError(f"HTTP {r.status_code}: {text[:200]}")
    if text.startswith("ERROR"):
        # напр. "ERROR 50 :: NOTHING FOUND" — трактуємо як порожні дані
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


def domain_overview(domain: str) -> Dict[str, Any]:
    """Загальні лічильники: організ. ключі (Or), організ. трафік (Ot)."""
    text = _request({
        "type": "domain_ranks",
        "domain": domain,
        "database": config.SEMRUSH_DB,
        "export_columns": "Dn,Rk,Or,Ot,Oc",
    })
    rows = _parse_csv(text)
    if not rows:
        return {"organic_keywords": 0, "organic_traffic": 0, "rank": None}
    row = rows[0]
    def _int(k):
        try:
            return int(float(row.get(k, "0") or 0))
        except ValueError:
            return 0
    return {
        "organic_keywords": _int("Organic Keywords"),
        "organic_traffic": _int("Organic Traffic"),
        "rank": row.get("Rank"),
    }


def organic_keywords(domain: str, pos_min: int, pos_max: int,
                     limit: int = 2000) -> List[Dict[str, Any]]:
    """Органічні ключі домену у діапазоні позицій [pos_min, pos_max].
    Повертає list dict: keyword, position, volume, cpc, competition, kd, intent, url.
    Пейджинг по 1000 (макс. для одного запиту API)."""
    collected: List[Dict[str, Any]] = []
    offset = 0
    page = 1000
    # SemRush filter syntax: <sign>|<field>|<op>|<value>, поєднання через "|"
    dfilter = f"+|Po|Gt|{pos_min - 1}|+|Po|Lt|{pos_max + 1}"
    while offset < limit:
        text = _request({
            "type": "domain_organic",
            "domain": domain,
            "database": config.SEMRUSH_DB,
            "display_limit": min(page, limit - offset),
            "display_offset": offset,
            "display_sort": "nq_desc",
            "display_filter": dfilter,
            "export_columns": "Ph,Po,Nq,Cp,Co,Kd,In,Ur",
        })
        rows = _parse_csv(text)
        if not rows:
            break
        for row in rows:
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
        if len(rows) < page:
            break
        offset += page
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
