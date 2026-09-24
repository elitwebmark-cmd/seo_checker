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

    # 5b) динаміка сегментів нашого сайту + тренд
    our_history = res.get("position_history") or []
    seg_trend = _seg_trend(our_history)

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
            "our_p11_20": our_seg["p11_20"],
            "competitors": competitors,
            "biggest": biggest,
            "gap_rows": gap["rows"],
            "total_missed": gap["total_missed"],
            "seg_trend": seg_trend,
        })
    except Exception:
        log.exception("AI competitor_analysis failed")

    # 7) змістовні fallback-тексти (щоб звіт був насичений і без AI)
    fb = _fallback_texts(domain, our, competitors, biggest, gap, seg_trend)

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
        "our_history": our_history,
        "seg_trend": seg_trend,
        "ai": ai,
        "fb": fb,
    }


def _pct(new, old):
    if not old:
        return None
    return round((new - old) / old * 100)


def _seg_trend(history):
    """Динаміка сегментів: перший vs останній місяць періоду."""
    pts = [p for p in (history or []) if p.get("segments")]
    if len(pts) < 2:
        return None
    a, b = pts[0]["segments"], pts[-1]["segments"]
    keys = ["top3", "p4_10", "p11_20", "p21_50", "p51_100"]
    seg = {}
    for k in keys:
        fr, to = int(a.get(k) or 0), int(b.get(k) or 0)
        seg[k] = {"from": fr, "to": to, "delta": to - fr, "pct": _pct(to, fr)}
    tot_a = sum(int(a.get(k) or 0) for k in keys)
    tot_b = sum(int(b.get(k) or 0) for k in keys)
    return {
        "from_date": pts[0].get("date"), "to_date": pts[-1].get("date"),
        "months": len(pts), "seg": seg,
        "total": {"from": tot_a, "to": tot_b, "delta": tot_b - tot_a, "pct": _pct(tot_b, tot_a)},
        "commercial": {  # ТОП3 + 4–10 як «робочі» комерційні позиції
            "from": seg["top3"]["from"] + seg["p4_10"]["from"],
            "to": seg["top3"]["to"] + seg["p4_10"]["to"],
        },
    }


def _fmt(n):
    try:
        return f"{int(round(n)):,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(n)


def _seg_trend_text(domain, st):
    if not st:
        return ""
    d = st["seg"]
    t3, p410 = d["top3"], d["p4_10"]
    comm_from = st["commercial"]["from"]
    comm_to = st["commercial"]["to"]
    comm_delta = comm_to - comm_from

    def mv(x):
        if x > 0:
            return f"зросла на {x}"
        if x < 0:
            return f"скоротилася на {abs(x)}"
        return "не змінилася"
    parts = [
        f"За {st['months']} міс кількість ключів у ТОП-3 {mv(t3['delta'])} "
        f"(з {_fmt(t3['from'])} до {_fmt(t3['to'])}), а в зоні 4–10 — {mv(p410['delta'])} "
        f"(з {_fmt(p410['from'])} до {_fmt(p410['to'])}).",
    ]
    if comm_delta > 0:
        parts.append(f"Сумарно «робочих» комерційних позицій (ТОП-3 + 4–10) стало більше на "
                     f"{comm_delta} — це позитивний сигнал, але темп нарощення повільний "
                     f"порівняно з потенціалом ніші.")
    elif comm_delta < 0:
        parts.append(f"Сумарно «робочих» комерційних позицій (ТОП-3 + 4–10) стало менше на "
                     f"{abs(comm_delta)} — сайт втрачає видимість у найдохіднішій зоні видачі, "
                     f"і цей трафік перетікає до конкурентів.")
    else:
        parts.append("Кількість «робочих» комерційних позицій майже не змінюється — сайт "
                     "стагнує там, де конкуренти активно ростуть.")
    p2150 = d["p21_50"]["to"] + d["p51_100"]["to"]
    parts.append(f"При цьому {_fmt(p2150)} ключів «застрягли» у зоні 21–100 — це прямий резерв "
                 f"зростання: підняття їх у ТОП-10 дає найшвидший приріст трафіку.")
    return " ".join(parts)


def _fallback_texts(domain, our, competitors, biggest, gap, seg_trend):
    """Готові змістовні тексти на випадок відсутності AI-ключа."""
    rows = gap.get("rows") or []
    total_missed = gap.get("total_missed") or 0
    top_gap = rows[:6]
    summary = (
        f"Сайт {domain} має {_fmt(our['organic_traffic'])} органічних візитів/міс і "
        f"{_fmt(our['organic_keywords'])} ключів у видачі. У своїй ніші він конкурує з "
        f"{len(competitors)} сильнішими гравцями, які сумарно забирають близько "
        f"{_fmt(total_missed)} візитів/міс за комерційними запитами, де вони в ТОП, а ви — ні. "
        f"Це не втрачений назавжди трафік, а прямий резерв: попит уже існує, його лише перехоплюють конкуренти.")
    if biggest:
        landscape = (
            f"Найсильніший конкурент — {biggest['domain']}: {_fmt(biggest['organic_traffic'])} "
            f"візитів/міс, що у {biggest.get('bigger_x','?')}× більше за ваш сайт, і "
            f"{_fmt(biggest['organic_keywords'])} ключів проти ваших {_fmt(our['organic_keywords'])}. "
            f"Перевага будується насамперед у комерційній зоні видачі: у конкурентів помітно більше "
            f"ключів у ТОП-3 і 4–10. Саме там формується основний трафік і заявки, і саме там "
            f"зосереджений розрив, який треба закривати.")
    else:
        landscape = ("Конкуренти переважають вас за обсягом органічного трафіку й кількістю ключів "
                     "у комерційній зоні видачі.")
    losses = []
    for g in top_gap:
        pos = "поза ТОП-100" if not g.get("our_pos") else f"на позиції {g['our_pos']}"
        losses.append({
            "title": f"«{g['keyword']}» — {_fmt(g['missed_traffic'])} візитів/міс повз вас",
            "detail": (f"За запитом частотністю {_fmt(g['volume'])}/міс ви {pos}, тоді як "
                       f"{g['best_comp_domain']} тримає #{g['best_comp_pos']}. Через це ви "
                       f"недоотримуєте близько {_fmt(g['missed_traffic'])} цільових візитів щомісяця — "
                       f"це готові клієнти з комерційним наміром, які йдуть до конкурента."),
        })
    actions = [
        {"title": "Закрити пріоритетні запити-розриви",
         "detail": "Створити/підсилити посадкові під запити з таблиці, де конкуренти в ТОП, а ви — ні. "
                   "Почати з найчастотніших комерційних — вони дають найбільший приріст.",
         "effect": f"повернення до ~{_fmt(total_missed)} візитів/міс поступово"},
        {"title": "Підняти ключі із зони 21–100 у ТОП-10",
         "detail": "У вас сотні ключів «застрягли» на 3–10 сторінках видачі. Це найдешевший приріст: "
                   "доопрацювання контенту, перелінковка й метадані піднімають їх у зону трафіку.",
         "effect": "швидкий приріст трафіку без нових сторінок"},
        {"title": "Наростити тематичну глибину під нішу",
         "detail": "Конкуренти виграють за рахунок ширшого семантичного покриття. Потрібен контент-план "
                   "по кластерах, яких у вас бракує, з пріоритетом на комерційні кластери.",
         "effect": "зростання к-сті ключів і охоплення попиту"},
        {"title": "Технічне SEO та швидкість",
         "detail": "Прибрати технічні бар'єри індексації й прискорити сайт — це підсилює ранжування всіх "
                   "сторінок одразу і покращує конверсію.",
         "effect": "кращі позиції + вища конверсія трафіку"},
        {"title": "Системна робота за моделлю «оплата за вихід у ТОП»",
         "detail": "Закривати розрив планомірно, місяць за місяцем, з фокусом на комерційні запити та "
                   "прозорою звітністю по позиціях і трафіку.",
         "effect": "передбачуване повернення частки ринку"},
    ]
    conclusion = (
        f"Конкуренти забирають близько {_fmt(total_missed)} візитів/міс за комерційними запитами, де "
        f"вони в ТОП, а {domain} — ні. Попит сформований, ніша прибуткова, а розрив здебільшого у "
        f"комерційній зоні видачі — тобто його реально закрити системним SEO. Рекомендуємо стартувати "
        f"з пріоритетних запитів-розривів за напрямком «оплата за вихід у ТОП».")
    return {
        "summary": summary, "landscape": landscape,
        "seg_trend_text": _seg_trend_text(domain, seg_trend),
        "losses": losses, "actions": actions, "conclusion": conclusion,
    }


def _niche_str(res):
    ni = res.get("niche") or {}
    parts = [ni.get("direction_name"), ni.get("industry_name"), ni.get("subniche")]
    return " · ".join([p for p in parts if p]) or "—"
