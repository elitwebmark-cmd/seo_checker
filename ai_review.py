# -*- coding: utf-8 -*-
"""AI-аналітика через Claude (Anthropic Messages API):
- seo_review(domain, res)  — якісний SEO-аналіз on-page + метрик;
- exec_summary(res)        — стратегічне резюме всього звіту + пріоритети.
Sonnet з фолбеком на Haiku. Кеш по домену. Без ключа/помилки -> None."""
from __future__ import annotations
import time
import json
import re
import logging
import requests
import config

log = logging.getLogger("ai_review")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_CACHE = {}


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


def _complete(system: str, prompt: str, max_tokens: int = 1100) -> str:
    if not config.ANTHROPIC_API_KEY:
        return None
    headers = {"x-api-key": config.ANTHROPIC_API_KEY,
               "anthropic-version": "2023-06-01", "content-type": "application/json"}
    for model in (config.AI_REVIEW_MODEL, config.AI_REVIEW_FALLBACK_MODEL):
        try:
            r = requests.post(ANTHROPIC_URL, headers=headers, timeout=config.AI_REVIEW_TIMEOUT,
                              json={"model": model, "max_tokens": max_tokens, "system": system,
                                    "messages": [{"role": "user", "content": prompt}]})
            if r.status_code >= 400:
                log.warning("AI %s -> HTTP %s: %s", model, r.status_code, r.text[:160])
                continue
            return (r.json().get("content") or [{}])[0].get("text", "")
        except Exception as e:
            log.warning("AI %s error: %s", model, str(e)[:160])
    return None


def debug() -> dict:
    """Діагностика моделей: чи є ключ і які моделі відповідають."""
    out = {"has_key": bool(config.ANTHROPIC_API_KEY),
           "model": config.AI_REVIEW_MODEL, "fallback": config.AI_REVIEW_FALLBACK_MODEL}
    if not config.ANTHROPIC_API_KEY:
        out["error"] = "ANTHROPIC_API_KEY не заданий"
        return out
    headers = {"x-api-key": config.ANTHROPIC_API_KEY,
               "anthropic-version": "2023-06-01", "content-type": "application/json"}
    for label, model in (("primary", config.AI_REVIEW_MODEL), ("fallback", config.AI_REVIEW_FALLBACK_MODEL)):
        try:
            r = requests.post(ANTHROPIC_URL, headers=headers, timeout=20,
                              json={"model": model, "max_tokens": 20,
                                    "messages": [{"role": "user", "content": "ping"}]})
            out[label] = {"model": model, "status": r.status_code,
                          "ok": r.status_code < 400,
                          "body": (None if r.status_code < 400 else r.text[:200])}
        except Exception as e:
            out[label] = {"model": model, "error": str(e)[:200]}
    return out


def _parse_json(text: str):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _lst(v):
    return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []


# ---------------- SEO-ревʼю ----------------
_SEO_SYS = ("Ти senior SEO-аналітик. Проаналізуй сайт за наданими даними та поверни "
            "ЛИШЕ JSON без пояснень, українською, конкретно й без води.")


def seo_review(domain: str, res: dict) -> dict:
    if not config.ANTHROPIC_API_KEY:
        return None
    return _cached(f"aiseo:{domain}", lambda: _seo_review(domain, res))


def _seo_review(domain: str, res: dict) -> dict:
    onp = {}
    try:
        import onpage
        o = onpage.analyze_site(domain)
        onp = (o or {}).get("home") or {}
    except Exception:
        onp = {}
    ni = res.get("niche") or {}
    mt = res.get("metrics") or {}
    kws = [q.get("keyword") for q in (res.get("dotisk_queries") or []) if q.get("keyword")][:15]
    prompt = (
        f"Домен: {domain}\n"
        f"Ніша: {ni.get('direction_name')} → {ni.get('industry_name')} → {ni.get('subniche')}\n"
        f"Метрики SemRush: орг. трафік {mt.get('organic_traffic')}/міс, "
        f"орг. ключів {mt.get('organic_keywords')}, комерц. запитів 4–20: "
        f"{mt.get('commercial_kw_11_30')}\n"
        f"On-page головної: title={onp.get('title')!r}; H1={onp.get('h1')!r}; "
        f"meta description={(onp.get('description') or '')[:300]!r}; "
        f"обсяг тексту, симв.={onp.get('text_chars')}\n"
        f"Топ комерційні запити: {', '.join(kws) or '—'}\n\n"
        'Поверни JSON: {"verdict":"1-2 речення загальний висновок по SEO",'
        '"strengths":["сильні сторони"],"weaknesses":["слабкі сторони"],'
        '"gaps":["семантичні/тематичні прогалини — яких тем чи типів сторінок бракує під нішу"],'
        '"recommendations":["конкретні пріоритетні дії"]}. У кожному списку 3-5 пунктів.')
    obj = _parse_json(_complete(_SEO_SYS, prompt, 1100))
    if not obj:
        return None
    return {
        "checked": True,
        "verdict": str(obj.get("verdict") or "").strip(),
        "strengths": _lst(obj.get("strengths")),
        "weaknesses": _lst(obj.get("weaknesses")),
        "gaps": _lst(obj.get("gaps")),
        "recommendations": _lst(obj.get("recommendations")),
    }


# ---------------- Executive summary ----------------
_SUM_SYS = ("Ти маркетинг-стратег агенції. На основі зведення каналів дай стислий "
            "стратегічний висновок і пріоритети. Поверни ЛИШЕ JSON, українською, без води.")


def exec_summary(res: dict) -> dict:
    if not config.ANTHROPIC_API_KEY:
        return None
    key = f"aisum:{res.get('domain','')}"
    return _cached(key, lambda: _exec_summary(res))


def _exec_summary(res: dict) -> dict:
    ni = res.get("niche") or {}
    mt = res.get("metrics") or {}
    bn = res.get("benefit") or {}
    ads = res.get("ads") or {}
    meta = res.get("meta_ads") or {}
    cro = res.get("cro") or {}
    rt = res.get("retention") or {}
    facts = [
        f"Домен: {res.get('domain')}",
        f"Вердикт кваліфікації: {res.get('verdict')} (бал {res.get('score')})",
        f"Ніша: {ni.get('industry_name')} → {ni.get('subniche')}",
        f"SEO: трафік {mt.get('organic_traffic')}/міс, ключів {mt.get('organic_keywords')}, "
        f"комерц. 4–20: {mt.get('commercial_kw_11_30')}",
    ]
    if bn.get("queries"):
        facts.append(f"Потенціал SEO у ТОП-1: +{bn.get('uplift')} візитів/міс, "
                     f"+{bn.get('profit_uplift')} ₴ прибутку/міс")
    if ads.get("checked"):
        facts.append(f"Контекст: {'працює ~'+str(ads.get('count'))+' оголош.' if ads.get('running') else 'не крутиться'}")
    if meta.get("checked"):
        facts.append(f"Meta-таргет: {'працює '+str(meta.get('count'))+' крео' if meta.get('running') else 'не активний'}")
    if cro.get("checked"):
        facts.append(f"CRO-бал: {cro.get('score_total')}/100 ({cro.get('score_label')})")
    if rt.get("checked"):
        facts.append(f"Retention: LTV-прибуток {rt.get('ltv_profit')} ₴/клієнт, "
                     f"потенціал програми +{rt.get('monthly_extra_profit')} ₴/міс")
    prompt = ("Зведення по каналах:\n" + "\n".join(facts) + "\n\n"
              'Поверни JSON: {"summary":"3-5 речень стратегічного висновку для клієнта",'
              '"priorities":[{"title":"дія","why":"чому саме це і який ефект"}]}. '
              "Пріоритетів 3-5, у порядку важливості.")
    obj = _parse_json(_complete(_SUM_SYS, prompt, 1000))
    if not obj:
        return None
    prios = []
    for p in (obj.get("priorities") or []):
        if isinstance(p, dict) and p.get("title"):
            prios.append({"title": str(p["title"]).strip(), "why": str(p.get("why") or "").strip()})
    return {"checked": True, "summary": str(obj.get("summary") or "").strip(), "priorities": prios}
