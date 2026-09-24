# -*- coding: utf-8 -*-
"""Збір даних для PDF «Конкурентний аналіз»: наш сайт + більші конкуренти
(трафік, сегменти позицій, потенціал), keyword-gap (де конкуренти в ТОП, а ми ні,
і скільки трафіку через це недоотримуємо) + розгорнуті AI-пояснення.

Повертає готовий dict для шаблону competitor_report.html."""
from __future__ import annotations
import logging
import config
import semrush

log = logging.getLogger("competitor_report")

_SEG_KEYS = ["top3", "p4_10", "p11_20", "p21_50", "p51_100"]


def _seg_dict(seg):
    s = (seg or {}).get("segments") or {}
    total = (seg or {}).get("total") or sum(int(s.get(k) or 0) for k in _SEG_KEYS)
    return {k: int(s.get(k) or 0) for k in _SEG_KEYS} | {"total": int(total or 0)}


def _site_data(domain, db, our_traffic=None):
    ov = {}
    try:
        ov = semrush.domain_overview(domain, db) or {}
    except Exception:
        pass
    try:
        seg = semrush.position_distribution(domain, db)
    except Exception:
        seg = None
    seg = _seg_dict(seg)
    ot = int(ov.get("organic_traffic") or 0)
    d = {
        "domain": domain,
        "organic_traffic": ot,
        "organic_keywords": int(ov.get("organic_keywords") or 0),
        "adwords_traffic": int(ov.get("adwords_traffic") or 0),
        "segments": seg,
        "top3": seg["top3"], "p4_10": seg["p4_10"], "p11_20": seg["p11_20"],
        "p21_50": seg["p21_50"], "p51_100": seg["p51_100"], "kw_top100": seg["total"],
    }
    if our_traffic:
        d["bigger_x"] = round(ot / our_traffic, 1) if our_traffic else None
    return d


def build(res: dict, db: str = None, competitor_domains=None) -> dict:
    """res — результат qualify по нашому домену (звідки беремо метрики/сегменти/
    історію/benefit). competitor_domains — необов'язковий ручний список; якщо не
    заданий, підбираємо БІЛЬШИХ конкурентів автоматично."""
    domain = res.get("domain")
    our_traffic = int((res.get("metrics") or {}).get("organic_traffic") or 0)

    # 1) конкуренти (більші за нас)
    if competitor_domains:
        comps_dom = [semrush._norm_domain(d) for d in competitor_domains if semrush._norm_domain(d)]
        comps_dom = [d for d in comps_dom if d != semrush._norm_domain(domain)][:5]
    else:
        comps_dom = [c["domain"] for c in
                     semrush.competitors_bigger(domain, db, need=config.COMPETITORS_LIMIT)]

    # 2) дані по кожному конкуренту
    competitors = [_site_data(d, db, our_traffic) for d in comps_dom]
    competitors = [c for c in competitors if c["organic_traffic"] > 0 or c["kw_top100"] > 0]

    # 3) наш сайт
    our_seg = _seg_dict(res.get("segments"))
    our = {
        "domain": domain,
        "organic_traffic": our_traffic,
        "organic_keywords": int((res.get("metrics") or {}).get("organic_keywords") or 0),
        "adwords_traffic": int((res.get("ads_traffic") or (res.get("paid") or {}).get("traffic") or 0)),
        "segments": our_seg,
        "top3": our_seg["top3"], "p4_10": our_seg["p4_10"], "p11_20": our_seg["p11_20"],
        "p21_50": our_seg["p21_50"], "p51_100": our_seg["p51_100"], "kw_top100": our_seg["total"],
        "is_self": True,
    }

    # 4) keyword gap (де конкуренти в ТОП, ми — ні)
    gap = semrush.keyword_gap(domain, comps_dom, db) if comps_dom else {"rows": [], "total_missed": 0}

    # 5) масштаб для стовпчикової діаграми трафіку
    all_sites = [our] + competitors
    max_traffic = max([s["organic_traffic"] for s in all_sites] + [1])
    biggest = max(competitors, key=lambda c: c["organic_traffic"], default=None)

    # 6) AI-аналіз
    ai = None
    try:
        import ai_review
        ai = ai_review.competitor_analysis(domain, {
            "sig": "|".join(sorted(comps_dom)),
            "niche": _niche_str(res),
            "our_traffic": our_traffic,
            "our_keywords": our["organic_keywords"],
            "our_top3": our_seg["top3"], "our_p4_10": our_seg["p4_10"],
            "competitors": competitors,
            "gap_rows": gap["rows"],
            "total_missed": gap["total_missed"],
        })
    except Exception:
        log.exception("AI competitor_analysis failed")

    return {
        "domain": domain,
        "res": res,                      # для історії/benefit/niche у шаблоні
        "our": our,
        "competitors": competitors,
        "all_sites": all_sites,
        "max_traffic": max_traffic,
        "biggest": biggest,
        "gap": gap["rows"],
        "gap_total_missed": gap["total_missed"],
        "ai": ai,
    }


def _niche_str(res):
    ni = res.get("niche") or {}
    parts = [ni.get("direction_name"), ni.get("industry_name"), ni.get("subniche")]
    return " · ".join([p for p in parts if p]) or "—"
