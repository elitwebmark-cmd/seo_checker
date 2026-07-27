"""Клієнт SemRush Analytics API (v3, api.semrush.com).
Використовує ключ SEMRUSH_API_KEY. База за замовч. — google.com.ua (ua)."""
from __future__ import annotations
import time
import requests
from typing import List, Dict, Any
import config


class SemrushError(Exception):
    pass


# --- Кеш по домену: не палити ліміти на повторних перевірках того самого сайту ---
_CACHE: Dict[str, Any] = {}


def _cached(key: str, producer):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and (now - hit[0]) < config.SEMRUSH_CACHE_TTL:
        return hit[1]
    val = producer()
    _CACHE[key] = (now, val)
    return val


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
    return _cached(f"ov:{_db(db)}:{domain}", lambda: _domain_overview(domain, db))


def _domain_overview(domain: str, db: str = None) -> Dict[str, Any]:
    # X0..XA — готовий розподіл орг. ключів по позиціях (Organic Position Distribution):
    # X0:1-3, X1:4-10, X2:11-20, X3:21-30, X4:31-40, X5:41-50, X6:51-60 ... XA:91-100.
    # Тягнемо його прямо тут (той самий overview-запит), без перебору ключів.
    cols = ["Dn", "Rk", "Or", "Ot", "Oc", "Ad", "At", "Ac",
            "X0", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "XA"]
    empty = {"organic_keywords": 0, "organic_traffic": 0, "rank": None,
             "adwords_keywords": 0, "adwords_traffic": 0, "adwords_cost": 0,
             "distribution": None}
    try:
        text = _request({
            "type": "domain_ranks",
            "domain": domain,
            "database": _db(db),
            "export_columns": ",".join(cols),
        })
    except SemrushError:
        return empty
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return empty
    # Значення повертаються у порядку запитаних колонок → мапимо по коду.
    row = dict(zip(cols, lines[1].split(";")))

    def gi(code):
        return _safe_int(row.get(code))

    x = [gi(f"X{n}") for n in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A")]
    total = sum(x)
    distribution = None
    if total > 0:
        seg = {"top3": x[0], "p4_10": x[1], "p11_20": x[2],
               "p21_50": x[3] + x[4] + x[5], "p51_100": x[6] + x[7] + x[8] + x[9] + x[10]}
        distribution = {"segments": seg, "labels": _SEG_LABELS, "total": total, "capped": False}
    return {
        "organic_keywords": gi("Or"),
        "organic_traffic": gi("Ot"),
        "rank": row.get("Rk"),
        "adwords_keywords": gi("Ad"),
        "adwords_traffic": gi("At"),
        "adwords_cost": gi("Ac"),
        "distribution": distribution,
    }


def domain_history(domain: str, db: str = None, limit: int = 10) -> List[Dict[str, Any]]:
    return _cached(f"hist:{_db(db)}:{domain}:{limit}", lambda: _domain_history(domain, db, limit))


def _domain_history(domain: str, db: str = None, limit: int = 10) -> List[Dict[str, Any]]:
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
    ctr1 = config.CTR_BY_POS[1]
    lo, hi = config.POS_MIN, config.POS_MAX
    agg = {}
    for row in _parse_csv(text):
        url = row.get("Url") or row.get("URL") or ""
        if not url:
            continue
        pos = _safe_int(row.get("Position"))
        vol = _safe_int(row.get("Search Volume"))
        a = agg.setdefault(url, {"url": url, "keywords": 0, "q_4_20": 0,
                                 "traffic": 0.0, "traffic_pot": 0.0})
        a["keywords"] += 1
        a["traffic"] += vol * _ctr(pos)
        if lo <= pos <= hi:                 # запити в зоні дотиску ТОП 4–20
            a["q_4_20"] += 1
            a["traffic_pot"] += vol * ctr1  # припускаємо вихід у ТОП-1
        else:
            a["traffic_pot"] += vol * _ctr(pos)
    pages = sorted(agg.values(), key=lambda x: x["traffic"], reverse=True)[:limit]
    for p in pages:
        p["traffic"] = int(round(p["traffic"]))
        p["traffic_pot"] = int(round(p["traffic_pot"]))
    return pages


_SEG_BUCKETS = [("top3", 1, 3), ("p4_10", 4, 10), ("p11_20", 11, 20),
                ("p21_50", 21, 50), ("p51_100", 51, 100)]
_SEG_LABELS = {"top3": "ТОП 3", "p4_10": "4–10", "p11_20": "11–20",
               "p21_50": "21–50", "p51_100": "51–100"}


def position_segments(domain: str, db: str = None, limit: int = None) -> Dict[str, Any]:
    """Розподіл органічних ключів по сегментах позицій (зріз на зараз).
    Тягне позиції 1–100 (сорт. за позицією) і рахує кількість у кожному сегменті."""
    limit = int(limit or config.SEGMENT_FETCH_LIMIT)
    seg = {name: 0 for name, _, _ in _SEG_BUCKETS}
    try:
        text = _request({
            "type": "domain_organic",
            "domain": domain,
            "database": _db(db),
            "display_limit": max(1, limit),
            "display_sort": "po_asc",
            "display_filter": "+|Po|Lt|101",
            "export_columns": "Po",
        })
    except SemrushError:
        return {"segments": seg, "labels": _SEG_LABELS, "total": 0, "capped": False}
    n = 0
    for row in _parse_csv(text):
        p = _safe_int(row.get("Position"))
        if p <= 0:
            continue
        n += 1
        for name, lo, hi in _SEG_BUCKETS:
            if lo <= p <= hi:
                seg[name] += 1
                break
    return {"segments": seg, "labels": _SEG_LABELS, "total": n, "capped": n >= limit}


def organic_all(domain: str, db: str = None, limit: int = None) -> List[Dict[str, Any]]:
    """ОДИН витяг domain_organic (позиції 1–100) — для комерц. запитів 4–20,
    потенціалу, ТОП-сторінок і фолбек-матриці. Кешується по домену.
    Матрицю за наявності беремо з overview (X0..XA), тут — резервний розрахунок."""
    lim = int(limit or config.ORGANIC_FETCH_LIMIT)
    return _cached(f"org:{_db(db)}:{domain}:{lim}", lambda: _organic_all(domain, db, lim))


def _organic_all(domain: str, db: str, lim: int) -> List[Dict[str, Any]]:
    try:
        text = _request({
            "type": "domain_organic",
            "domain": domain,
            "database": _db(db),
            "display_limit": max(1, lim),
            "display_sort": "po_asc",
            "display_filter": "+|Po|Lt|101",
            "export_columns": "Ph,Po,Nq,Cp,Co,Kd,In,Ur",
        })
    except SemrushError:
        return []
    out = []
    for row in _parse_csv(text):
        out.append({
            "keyword": row.get("Keyword", ""),
            "position": _safe_int(row.get("Position")),
            "volume": _safe_int(row.get("Search Volume")),
            "cpc": _safe_float(row.get("CPC")),
            "competition": _safe_float(row.get("Competition")),
            "kd": _safe_float(row.get("Keyword Difficulty")),
            "intent": (row.get("Intents", "") or "").split(",")[0].strip(),
            "url": row.get("Url", ""),
        })
    return out


def segments_from(rows: List[Dict[str, Any]], limit: int = None) -> Dict[str, Any]:
    """Матриця сегментів позицій з уже витягнутих рядків (без нового запиту)."""
    seg = {name: 0 for name, _, _ in _SEG_BUCKETS}
    n = 0
    for r in rows:
        p = r.get("position") or 0
        if p <= 0:
            continue
        n += 1
        for name, lo, hi in _SEG_BUCKETS:
            if lo <= p <= hi:
                seg[name] += 1
                break
    capped = bool(limit and len(rows) >= limit)
    return {"segments": seg, "labels": _SEG_LABELS, "total": n, "capped": capped}


def pages_from(rows: List[Dict[str, Any]], limit: int = 15) -> List[Dict[str, Any]]:
    """ТОП-сторінки по трафіку з уже витягнутих рядків (без нового запиту)."""
    ctr1 = config.CTR_BY_POS[1]
    lo, hi = config.POS_MIN, config.POS_MAX
    agg = {}
    for r in rows:
        url = r.get("url") or ""
        if not url:
            continue
        pos = r.get("position") or 99
        vol = r.get("volume") or 0
        a = agg.setdefault(url, {"url": url, "keywords": 0, "q_4_20": 0,
                                 "traffic": 0.0, "traffic_pot": 0.0})
        a["keywords"] += 1
        a["traffic"] += vol * _ctr(pos)
        if lo <= pos <= hi:
            a["q_4_20"] += 1
            a["traffic_pot"] += vol * ctr1
        else:
            a["traffic_pot"] += vol * _ctr(pos)
    pages = sorted(agg.values(), key=lambda x: x["traffic"], reverse=True)[:limit]
    for p in pages:
        p["traffic"] = int(round(p["traffic"]))
        p["traffic_pot"] = int(round(p["traffic_pot"]))
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
