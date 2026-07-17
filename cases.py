# -*- coding: utf-8 -*-
"""Підбір релевантних кейсів Elit-Web за нішею сайту.
Тягне довідник кейсів (Google CSV), кешує, для кожного кейсу евристично
визначає нашу галузь/піднішу (категоризація в довіднику своя) і матчить."""
from __future__ import annotations
import os, re, time, threading, csv, io
import requests
import config, niche

TTL = int(os.getenv("CASES_CACHE_TTL", "600"))

_CACHE = {"ts": 0.0, "cases": []}
_LOCK = threading.Lock()

COUNTRY_FLAG = {
    "україна": "🇺🇦", "украина": "🇺🇦", "польща": "🇵🇱", "польша": "🇵🇱",
    "німеччина": "🇩🇪", "германия": "🇩🇪", "велика британія": "🇬🇧", "великобритания": "🇬🇧",
    "сша": "🇺🇸", "usa": "🇺🇸", "світ": "🌍", "мир": "🌍", "world": "🌍", "казахстан": "🇰🇿",
    "молдова": "🇲🇩", "румунія": "🇷🇴", "європа": "🇪🇺",
}

# назви колонок (можуть трохи відрізнятись — шукаємо гнучко)
def _col(headers, *names):
    low = [h.strip().lower() for h in headers]
    for n in names:
        n = n.lower()
        for i, h in enumerate(low):
            if n in h:
                return i
    return None


def _norm_domain(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^https?://", "", s).split("/")[0]
    return s.replace("www.", "").strip(". ")


def _link(v: str) -> str:
    v = (v or "").strip()
    return v if v.startswith("http") else ""


def _build():
    url = config.CASES_SHEET_CSV
    if not url:
        return []
    r = requests.get(url, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.text)))
    if not rows:
        return []
    hdr = rows[0]
    ci = {
        "domain": _col(hdr, "домен"),
        "biz": _col(hdr, "тип бізнесу", "тип бизнеса"),
        "cat": _col(hdr, "категорія бізнесу", "категория"),
        "niche": _col(hdr, "ніша", "ниша"),
        "cniche": _col(hdr, "claudi niche", "claudi"),
        "country": _col(hdr, "країна", "страна"),
        "service": _col(hdr, "послуга", "услуга"),
        "kp": _col(hdr, "кейс для кп", "для кп"),
        "ext": _col(hdr, "росширений", "розширений", "расширенный"),
        "blog": _col(hdr, "блозі", "блоге", "стаття", "статья"),
    }

    def cell(row, key):
        i = ci.get(key)
        return (row[i].strip() if i is not None and i < len(row) else "")

    cases = []
    for row in rows[1:]:
        if not any(row):
            continue
        domain = _norm_domain(cell(row, "domain"))
        if not domain or "." not in domain:
            continue
        links = {"kp": _link(cell(row, "kp")), "ext": _link(cell(row, "ext")),
                 "blog": _link(cell(row, "blog"))}
        links = {k: v for k, v in links.items() if v}
        if not links:
            continue   # тільки кейси з посиланням
        niche_text = cell(row, "cniche") or cell(row, "niche")
        blob = " ".join([cell(row, "cniche"), cell(row, "niche"),
                         cell(row, "cat"), cell(row, "biz"), domain])
        cl = niche.classify(blob)
        country = cell(row, "country")
        cases.append({
            "domain": domain,
            "service": cell(row, "service") or "SEO",
            "country": country,
            "country_flag": COUNTRY_FLAG.get(country.strip().lower(), ""),
            "niche_text": niche_text,
            "links": links,
            "industry": cl.get("industry"),
            "subniche": cl.get("subniche_code"),
            "_words": set(re.findall(r"[a-zа-яіїєґ]{4,}", niche_text.lower())),
        })
    return cases


def _refresh(force=False):
    now = time.time()
    with _LOCK:
        if not force and _CACHE["cases"] and now - _CACHE["ts"] < TTL:
            return
    try:
        cases = _build()
    except Exception:
        return
    if cases:
        with _LOCK:
            _CACHE.update(ts=now, cases=cases)


def match(niche_info: dict, limit: int = 6) -> list:
    _refresh()
    with _LOCK:
        cases = list(_CACHE["cases"])
    if not cases or not niche_info:
        return []
    pind = niche_info.get("industry")
    psub = niche_info.get("subniche_code")
    pwords = set(re.findall(r"[a-zа-яіїєґ]{4,}",
                 ((niche_info.get("subniche") or "") + " " +
                  (niche_info.get("industry_name") or "")).lower()))
    scored = []
    for c in cases:
        s = 0
        if psub and c["subniche"] == psub:
            s += 100
        if pind and c["industry"] == pind:
            s += 40
        s += len(pwords & c["_words"]) * 6
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    # прибираємо дублі доменів, лишаємо найкращі
    seen, out = set(), []
    for s, c in scored:
        if c["domain"] in seen:
            continue
        seen.add(c["domain"]); out.append(c)
        if len(out) >= limit:
            break
    return out
