"""Перевірка, чи домен уже є клієнтом Elit-Web.
Тягне список із Google-таблиці (CSV), кешує в памʼяті, нормалізує й зіставляє
за точним збігом та за 'підозріло схожим' (той самий бренд / висока схожість)."""
from __future__ import annotations
import os, re, time, threading, difflib
import requests
import config

TTL = int(os.getenv("CLIENTS_CACHE_TTL", "300"))       # кеш списку, c
FUZZY_MIN = float(os.getenv("CLIENTS_FUZZY_MIN", "0.90"))

_ZW = {"​", "‌", "‍", "﻿", " "}
_DOMAIN_RE = re.compile(r"([a-z0-9\-]+\.)+[a-z]{2,}")
# багатоскладові TLD (Україна тощо) — перевіряти першими
_MULTI_TLD = [".com.ua", ".co.ua", ".in.ua", ".biz.ua", ".org.ua", ".net.ua",
              ".kyiv.ua", ".pp.ua", ".km.ua", ".lviv.ua"]

_CACHE = {"ts": 0.0, "hosts": set(), "brands": {}}   # brand -> set(hosts)
_LOCK = threading.Lock()


def _clean(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch not in _ZW).strip().lower()


def normalize(host: str) -> str:
    h = _clean(host)
    h = re.sub(r"^https?://", "", h).split("/")[0].split("?")[0]
    if h.startswith("www."):
        h = h[4:]
    return h.strip(". ")


def brand(host: str) -> str:
    """Реєстрове імʼя (бренд) без TLD і піддоменів."""
    h = normalize(host)
    for suf in sorted(_MULTI_TLD, key=len, reverse=True):
        if h.endswith(suf):
            h = h[:-len(suf)]
            break
    else:
        if "." in h:
            h = h.rsplit(".", 1)[0]
    return h.split(".")[-1] if "." in h else h   # останній label (відкидаємо піддомени)


def _parse(text: str):
    hosts, brands = set(), {}
    for line in text.splitlines():
        for m in _DOMAIN_RE.finditer(_clean(line)):
            host = normalize(m.group(0))
            if not host or "." not in host:
                continue
            hosts.add(host)
            b = brand(host)
            if len(b) >= 3:
                brands.setdefault(b, set()).add(host)
    return hosts, brands


def _refresh(force=False):
    now = time.time()
    with _LOCK:
        if not force and _CACHE["hosts"] and now - _CACHE["ts"] < TTL:
            return
    url = config.CLIENTS_SHEET_CSV
    if not url:
        return
    try:
        r = requests.get(url, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        hosts, brands = _parse(r.text)
    except Exception:
        return
    if hosts:
        with _LOCK:
            _CACHE.update(ts=now, hosts=hosts, brands=brands)


def check(domain: str) -> dict:
    """Повертає {is_client, level, matched}. level: exact|similar|suspect|None."""
    _refresh()
    with _LOCK:
        hosts = set(_CACHE["hosts"])
        brands = {k: set(v) for k, v in _CACHE["brands"].items()}
    if not hosts:
        return {"is_client": False, "level": None, "matched": None}

    h = normalize(domain)
    if h in hosts:
        return {"is_client": True, "level": "exact", "matched": h}

    b = brand(h)
    # той самий бренд, але інший TLD/піддомен (напр. brand.ua vs brand.com.ua)
    if len(b) >= 3 and b in brands:
        return {"is_client": True, "level": "similar", "matched": sorted(brands[b])[0]}

    # нечітка схожість (одруківки, дефіси тощо)
    best, best_host = 0.0, None
    for ch in hosts:
        rr = difflib.SequenceMatcher(None, h, ch).ratio()
        if rr > best:
            best, best_host = rr, ch
    if best >= FUZZY_MIN:
        return {"is_client": True, "level": "suspect", "matched": best_host}
    return {"is_client": False, "level": None, "matched": None}
