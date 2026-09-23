"""Traffic Analytics (домен -> загальний трафік + канали) через Semrush-сумісний
проксі (api-semrush.groupbuyseo.org, окремий ключ SEMRUSH_TA_KEY — не плутати зі
звичайним Analytics API в semrush.py).

Канали рахуються НЕ з summary (там колонки direct/referral/... на цьому ключі
майже завжди порожні), а з ендпоінта `sources`: беремо ранжований список джерел,
класифікуємо кожен хост (пошуковик/соц/AI/реферал/direct) і агрегуємо по частках
traffic_share, множимо на надійний total visits із summary. Paid береться окремо
зі стандартного AdWords-трафіку (передається аргументом), бо цей проксі не
розрізняє paid/organic усередині "search".

Застереження, підтверджені на живих даних:
1) без явного display_date проксі віддає дані на ~2 місяці старіші — просимо
   останній завершений місяць з фолбеком на дефолт;
2) "ERROR 503 :: TRENDS_UNAVAILABLE" трапляється періодично навіть для валідних
   запитів — робимо один ретрай.
"""
from __future__ import annotations
import time
from datetime import date
import requests
from typing import Any, Dict, List, Optional
import config


class TrafficError(Exception):
    pass


_CACHE: Dict[str, Any] = {}


def _ttl() -> int:
    return getattr(config, "SEMRUSH_TA_CACHE_TTL", 604800)


def _key() -> str:
    return getattr(config, "SEMRUSH_TA_KEY", "") or getattr(config, "SEMRUSH_API_KEY", "")


def _base() -> str:
    return getattr(config, "SEMRUSH_TA_BASE",
                   "https://api-semrush.groupbuyseo.org/analytics/ta/api/v3/")


def _timeout() -> int:
    return getattr(config, "SEMRUSH_TA_TIMEOUT", 20)


def _cached(key: str, producer):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and (now - hit[0]) < _ttl():
        return hit[1]
    val = producer()
    _CACHE[key] = (now, val)
    return val


def _get(path: str, params: Dict[str, Any], retries: int = 1) -> str:
    p = dict(params)
    p["key"] = _key()
    base = _base().rstrip("/") + "/"
    last_err = None
    for attempt in range(retries + 1):
        r = requests.get(base + path, params=p, timeout=_timeout())
        text = r.text.strip()
        if r.status_code == 200 and not text.startswith("ERROR"):
            return text
        last_err = TrafficError(
            f"HTTP {r.status_code}: {text[:200]}" if r.status_code != 200 else text)
        if attempt < retries:
            time.sleep(1.5)
    raise last_err


def _last_complete_month() -> str:
    today = date.today()
    y, m = today.year, today.month - 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y:04d}-{m:02d}-01"


def _get_dated(path: str, params: Dict[str, Any]) -> str:
    dated = dict(params)
    dated["display_date"] = _last_complete_month()
    try:
        return _get(path, dated)
    except TrafficError:
        return _get(path, params)


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


def summary(domain: str) -> Optional[Dict[str, Any]]:
    return _cached(f"ta:sum:{domain}", lambda: _summary(domain))


def _summary(domain: str) -> Optional[Dict[str, Any]]:
    try:
        text = _get_dated("summary", {"targets": domain})
    except TrafficError:
        return None
    rows = _parse_csv(text)
    if not rows:
        return None
    row = rows[0]
    visits = _safe_int(row.get("visits"))
    if visits <= 0:
        return None
    return {"visits": visits, "display_date": row.get("display_date", "")}


# Класифікація по exact-match хоста (без "www."), не по substring.
_SEARCH_ENGINES = {
    "google.com", "bing.com", "search.yahoo.com", "yahoo.com", "duckduckgo.com",
    "yandex.ru", "yandex.com", "yandex.ua", "baidu.com", "ecosia.org", "ask.com",
    "aol.com", "naver.com", "so.com", "sogou.com", "search.brave.com",
    "seznam.cz", "startpage.com", "qwant.com",
}
_SOCIAL_SITES = {
    "facebook.com", "m.facebook.com", "l.facebook.com", "lm.facebook.com",
    "instagram.com", "l.instagram.com", "tiktok.com", "twitter.com", "x.com",
    "t.co", "linkedin.com", "lnkd.in", "pinterest.com", "reddit.com",
    "old.reddit.com", "youtube.com", "m.youtube.com", "youtu.be",
    "telegram.org", "t.me", "whatsapp.com", "snapchat.com", "vk.com",
    "threads.net", "quora.com",
}
_AI_SITES = {
    "chatgpt.com", "chat.openai.com", "openai.com", "perplexity.ai",
    "gemini.google.com", "bard.google.com", "claude.ai", "copilot.microsoft.com",
    "you.com", "poe.com", "character.ai", "meta.ai", "grok.com", "x.ai",
    "deepseek.com", "chat.deepseek.com",
}


def _norm_host(h: str) -> str:
    h = (h or "").strip().lower()
    return h[4:] if h.startswith("www.") else h


def _classify_source(from_host: str, target: str) -> str:
    fh = _norm_host(from_host)
    tgt = _norm_host(target)
    if not fh:
        return "referral"
    if fh == tgt or fh.endswith("." + tgt):
        return "direct"
    if fh in _SEARCH_ENGINES:
        return "search"
    if fh in _AI_SITES:
        return "ai"
    if fh in _SOCIAL_SITES:
        return "social"
    return "referral"


def sources(domain: str, limit: int = 50) -> List[Dict[str, Any]]:
    return _cached(f"ta:src:{domain}:{limit}", lambda: _sources(domain, limit))


def _sources(domain: str, limit: int) -> List[Dict[str, Any]]:
    try:
        text = _get_dated("sources", {"target": domain, "display_limit": max(1, int(limit))})
    except TrafficError:
        return []
    out = []
    for r in _parse_csv(text):
        out.append({
            "from": r.get("from_target", ""),
            "share": _safe_float(r.get("traffic_share")),
            "visits": _safe_int(r.get("traffic")),
        })
    return out


def channel_breakdown(domain: str, limit: int = 50) -> Optional[Dict[str, Any]]:
    return _cached(f"ta:chan:{domain}:{limit}", lambda: _channel_breakdown(domain, limit))


def _channel_breakdown(domain: str, limit: int) -> Optional[Dict[str, Any]]:
    rows = _sources(domain, limit)
    if not rows:
        return None
    shares = {"direct": 0.0, "search": 0.0, "ai": 0.0, "social": 0.0, "referral": 0.0}
    covered = 0.0
    for r in rows:
        shares[_classify_source(r["from"], domain)] += r["share"]
        covered += r["share"]
    shares["other"] = max(0.0, 1.0 - covered)
    return {"channel_shares": shares}


def channel_matrix(domain: str, paid_traffic: int = 0) -> Optional[Dict[str, Any]]:
    """Повний розподіл каналів для порівняльного графіка: TA-канали
    (Direct/Organic/AI/Social/Referral/Other) + Paid Search окремо зі стандартного
    AdWords-трафіку. Total = TA-візити + paid, усі частки — відносно одного total."""
    if not _key():
        return None
    s = summary(domain)
    if not s:
        return None
    cb = channel_breakdown(domain)
    shares = dict(cb["channel_shares"]) if cb else {}
    ta_visits = s["visits"]
    paid = max(0, int(paid_traffic or 0))
    total = ta_visits + paid
    channels = {k: int(round(ta_visits * v)) for k, v in shares.items()}
    channels["paid"] = paid
    return {
        "domain": domain,
        "total": total,
        "display_date": s.get("display_date"),
        "channels": channels,
        "shares": {k: (v / total if total else 0.0) for k, v in channels.items()},
    }
