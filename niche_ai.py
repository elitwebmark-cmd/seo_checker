# -*- coding: utf-8 -*-
"""AI-класифікатор ніші через Claude Haiku (Anthropic Messages API).
Читає мета-теги сайту + топ органічні запити + домен і обирає ОДИН код підніші
з нашої таксономії. Кеш по домену. Фолбек на евристику робиться в qualify."""
from __future__ import annotations
import time
import json
import re
import requests
import config
import niche

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_CACHE = {}

_SYSTEM = ("Ти класифікуєш бізнес-сайт у нішу з фіксованого списку. "
           "Визнач ОСНОВНИЙ бізнес сайту (не побічні згадки) і обери ОДИН код підніші, "
           "що найкраще його описує. Враховуй домен і мета-теги більше, ніж органічні "
           "запити (вони можуть містити чужі теми). Відповідай ЛИШЕ JSON без пояснень.")


def _cached(key, producer):
    ttl = getattr(config, "SEMRUSH_CACHE_TTL", 604800)
    now = time.time()
    hit = _CACHE.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    val = producer()
    _CACHE[key] = (now, val)
    return val


def classify_ai(domain: str, meta_text: str, keywords: list) -> dict:
    if not config.ANTHROPIC_API_KEY:
        return None
    return _cached(f"nicheai:{domain}", lambda: _classify(domain, meta_text, keywords))


def _classify(domain: str, meta_text: str, keywords: list) -> dict:
    tax = "\n".join(niche.taxonomy_lines())
    kw = ", ".join([k for k in (keywords or []) if k][:12]) or "—"
    meta = (meta_text or "").strip()[:1500] or "—"
    prompt = (
        f"Домен: {domain}\n"
        f"Мета-теги сайту (title/description/keywords/H1/H2): {meta}\n"
        f"Топ органічні запити: {kw}\n\n"
        f"Список піднеш — обери код звідси:\n{tax}\n\n"
        'Поверни JSON: {"code":"<КОД зі списку>","confidence":"висока|середня|низька"}. '
        'Якщо визначити неможливо — {"code":null}.'
    )
    try:
        r = requests.post(
            ANTHROPIC_URL,
            headers={"x-api-key": config.ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config.NICHE_AI_MODEL, "max_tokens": 80,
                  "system": _SYSTEM,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=config.NICHE_AI_TIMEOUT)
        if r.status_code >= 400:
            return None
        text = (r.json().get("content") or [{}])[0].get("text", "")
    except Exception:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    code = (obj.get("code") or "").strip()
    conf = (obj.get("confidence") or "висока").strip()
    if not code:
        return None
    res = niche.result_for(code, conf)   # None, якщо код невалідний
    if res:
        res["ai"] = True
    return res
