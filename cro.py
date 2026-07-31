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
import logging
import requests
import config

log = logging.getLogger("cro")

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


def _login(force: bool = False) -> str:
    now = time.time()
    if not force and _TOKEN["v"] and now < _TOKEN["exp"]:
        return _TOKEN["v"]
    r = requests.post(
        config.CRO_BASE_URL.rstrip("/") + "/api/login",
        json={"username": config.CRO_LOGIN_USER, "password": config.CRO_LOGIN_PASSWORD},
        timeout=config.CRO_TIMEOUT)
    r.raise_for_status()
    tok = (r.json() or {}).get("token")
    _TOKEN["v"] = tok
    _TOKEN["exp"] = now + 900    # 15 хв (токен може інвалідуватись раніше)
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


def _audit_call(domain: str, lang: str, force_login: bool):
    tok = _login(force=force_login)
    if not tok:
        return None
    return requests.post(
        config.CRO_BASE_URL.rstrip("/") + "/api/audit",
        json={"url": _clean_domain(domain), "lang": lang},
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        timeout=config.CRO_AUDIT_TIMEOUT)


def _fetch(domain: str, lang: str) -> dict:
    try:
        r = _audit_call(domain, lang, force_login=False)
        if r is None:
            log.warning("CRO: логін не вдався для %s", domain)
            return None
        # токен протух/інвалідований -> перелогін і одна повторна спроба
        if r.status_code in (401, 403):
            log.info("CRO: %s -> %s, перелогін і повтор", domain, r.status_code)
            r = _audit_call(domain, lang, force_login=True)
        if r is None or r.status_code >= 400:
            log.warning("CRO: аудит %s -> HTTP %s", domain, getattr(r, "status_code", "None"))
            return None
        j = r.json()
    except Exception as e:
        log.warning("CRO: помилка аудиту %s: %s", domain, str(e)[:160])
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

    # priority у CRO приходить українською ("критично"/"важливо"/"покращення"),
    # інколи англійською — зводимо до канонічного слага для класів/фільтра.
    _SLUG = {"критично": "critical", "critical": "critical", "high": "critical",
             "важливо": "important", "important": "important", "medium": "important",
             "покращення": "improvement", "improvement": "improvement", "low": "improvement"}
    _LABEL = {"critical": "Критично", "important": "Важливо", "improvement": "Покращення"}
    raw_issues = [it for it in (a.get("issues") or []) if isinstance(it, dict)]
    id2title = {str(it.get("id")): it.get("title") for it in raw_issues if it.get("id")}
    issues = []
    for it in raw_issues:   # усі помилки
        praw = (it.get("priority") or "").strip().lower()
        slug = _SLUG.get(praw, "improvement")
        issues.append({"category": it.get("category"),
                       "priority": slug,                       # critical|important|improvement
                       "priority_label": _LABEL[slug],
                       "title": it.get("title"), "problem": it.get("problem"),
                       "impact": it.get("impact"), "benchmark": it.get("benchmark"),
                       "recommendation": it.get("recommendation")})

    # top_quick_wins повертає ID проблем — мапимо в заголовки (точки зростання).
    growth = []
    for q in (a.get("top_quick_wins") or []):
        t = id2title.get(str(q))
        if t:
            growth.append(t)
    if not growth:   # фолбек — заголовки критичних
        growth = [i["title"] for i in issues if i["priority"] == "critical" and i["title"]][:3]

    tot = a.get("score_total")
    return {
        "checked": True,
        "score_total": tot,
        "score_label": _score_label(tot),
        "categories": {k: _cat(k) for k in ("speed", "ux", "cta", "trust")},
        "summary": a.get("summary") or "",
        "quick_wins": growth,
        "issues": issues,
        "issues_total": len(issues),
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
