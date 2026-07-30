# -*- coding: utf-8 -*-
"""Інтеграція з CRO-аудитором Elit-Web (окремий сервіс).
Логін -> Bearer-токен -> POST /api/audit {url, lang} -> структурований JSON.
Кеш по домену (7 днів). Без логіну/помилки -> None, блок у звіті ховається.

API (розвідано з фронта CRO):
  POST /api/login  {username, password}                 -> {token}
  POST /api/audit  {url, lang}  Authorization: Bearer   -> {audit:{...}, pagespeed:{...}, screenshots:{...}}
"""
from __future__ import annotations
import time
import requests
import config

_CACHE = {}
_TOKEN = {"v": None, "exp": 0}


def _ready() -> bool:
    return bool(config.CRO_BASE_URL and config.CRO_LOGIN_USER and config.CRO_LOGIN_PASSWORD)


def _cached(key, producer):
    ttl = getattr(config, "SEMRUSH_CACHE_TTL", 604800)
    now = time.time()
    hit = _CACHE.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    val = producer()
    if val is not None:
        _CACHE[key] = (now, val)
    return val


def _login() -> str:
    now = time.time()
    if _TOKEN["v"] and now < _TOKEN["exp"]:
        return _TOKEN["v"]
    r = requests.post(
        config.CRO_BASE_URL.rstrip("/") + "/api/login",
        json={"username": config.CRO_LOGIN_USER, "password": config.CRO_LOGIN_PASSWORD},
        timeout=config.CRO_TIMEOUT)
    r.raise_for_status()
    tok = (r.json() or {}).get("token")
    _TOKEN["v"] = tok
    _TOKEN["exp"] = now + 3000   # ~50 хв
    return tok


def _score_label(score) -> str:
    if score is None:
        return ""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return ""
    if s >= 70:
        return "Добре"
    if s >= 50:
        return "Потребує уваги"
    return "Критично"


def _clean_domain(domain: str) -> str:
    d = (domain or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    return d.split("/")[0]


def audit(domain: str, lang: str = None) -> dict:
    if not _ready():
        return None
    lang = lang or config.CRO_LANG
    return _cached(f"cro:{domain}", lambda: _fetch(domain, lang))


def _fetch(domain: str, lang: str) -> dict:
    try:
        tok = _login()
        if not tok:
            return None
        r = requests.post(
            config.CRO_BASE_URL.rstrip("/") + "/api/audit",
            json={"url": _clean_domain(domain), "lang": lang},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            timeout=config.CRO_AUDIT_TIMEOUT)
        if r.status_code >= 400:
            return None
        j = r.json()
    except Exception:
        return None
    a = (j or {}).get("audit") or {}
    if not a:
        return None
    return _shape(a, j, j.get("pagespeed") or {})


def _shape(a, j, ps):
    cats = a.get("categories") or {}

    def _cat(k):
        c = cats.get(k) or {}
        return {"score": c.get("score"), "label": c.get("label")}

    _PRI = {"critical": "Критично", "high": "Критично",
            "important": "Важливо", "medium": "Важливо",
            "improvement": "Покращення", "low": "Покращення"}
    shots = j.get("screenshots") or {}
    issues = []
    for it in (a.get("issues") or []):   # усі помилки
        if isinstance(it, dict):
            praw = (it.get("priority") or "").strip().lower()
            zone = it.get("screenshot_zone") or it.get("screenshotZone")
            shot = shots.get(zone) if zone else None
            issues.append({"category": it.get("category"),
                           "priority": praw,                       # critical|important|improvement
                           "priority_label": _PRI.get(praw, "Покращення"),
                           "title": it.get("title"), "problem": it.get("problem"),
                           "impact": it.get("impact"), "benchmark": it.get("benchmark"),
                           "recommendation": it.get("recommendation"),
                           "screenshot_zone": zone, "screenshot": shot})
    tot = a.get("score_total")
    return {
        "checked": True,
        "score_total": tot,
        "score_label": _score_label(tot),
        "categories": {k: _cat(k) for k in ("speed", "ux", "cta", "trust")},
        "summary": a.get("summary") or "",
        "quick_wins": [w for w in (a.get("top_quick_wins") or []) if w],
        "issues": issues,
        "issues_total": len(issues),
        "screenshots": shots,
        "domain": j.get("url") or "",
        "pagespeed": {
            "score": ps.get("score"),
            "lcp": ps.get("lcp"), "fcp": ps.get("fcp"), "cls": ps.get("cls"),
            "tbt": ps.get("tbt"), "si": ps.get("si"),
        },
        "link": config.CRO_BASE_URL.rstrip("/"),
    }


def debug(domain: str) -> dict:
    """Діагностика: чи задані ключі, чи проходить логін, що повертає аудит."""
    out = {"ready": _ready(), "base_url": config.CRO_BASE_URL,
           "has_user": bool(config.CRO_LOGIN_USER), "has_pass": bool(config.CRO_LOGIN_PASSWORD)}
    if not _ready():
        out["error"] = "CRO_LOGIN_USER / CRO_LOGIN_PASSWORD не задані"
        return out
    try:
        lr = requests.post(config.CRO_BASE_URL.rstrip("/") + "/api/login",
                           json={"username": config.CRO_LOGIN_USER, "password": config.CRO_LOGIN_PASSWORD},
                           timeout=config.CRO_TIMEOUT)
        out["login_status"] = lr.status_code
        try:
            out["login_keys"] = list((lr.json() or {}).keys())
            out["got_token"] = bool((lr.json() or {}).get("token"))
        except Exception:
            out["login_body"] = lr.text[:200]
        if lr.status_code >= 400 or not (lr.json() or {}).get("token"):
            return out
        tok = lr.json()["token"]
    except Exception as e:
        out["login_error"] = str(e)[:300]
        return out
    try:
        ar = requests.post(config.CRO_BASE_URL.rstrip("/") + "/api/audit",
                           json={"url": _clean_domain(domain), "lang": config.CRO_LANG},
                           headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                           timeout=config.CRO_AUDIT_TIMEOUT)
        out["audit_status"] = ar.status_code
        try:
            j = ar.json()
            out["audit_top_keys"] = list((j or {}).keys())
            out["has_audit_obj"] = bool((j or {}).get("audit"))
            out["score_total"] = ((j or {}).get("audit") or {}).get("score_total")
        except Exception:
            out["audit_body"] = ar.text[:200]
    except Exception as e:
        out["audit_error"] = str(e)[:300]
    return out
