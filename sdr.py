# -*- coding: utf-8 -*-
"""Мапер даних кваліфікації (результат qualify) у поля конструктора холодної
відписки SDR (sdr.html). Повертає dict {ключ_поля: рядок}, яким JS на сторінці
підставляє значення у форму та рендерить лист + PDF-презентацію.

Ключі збігаються з id/data-k інпутів у sdr.html."""
from __future__ import annotations
import html as _html


def _esc(s) -> str:
    return _html.escape(str(s if s is not None else ""))


def _group(n) -> str:
    """12345 -> '12 345'. Нечислове/None -> ''."""
    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        return ""
    return f"{n:,}".replace(",", " ")


def _pct(x, dash_zero: bool = True) -> str:
    """0.307*100 вже у відсотках -> '30,7%'. Приймає число у відсотках."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return ""
    if dash_zero and v == 0:
        return ""
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return s.replace(".", ",") + "%"


def _num1(x) -> str:
    """Число з одним знаком: 1.2 -> '1,2', 13.0 -> '13'."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return ""
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _seg(segments: dict, key: str) -> str:
    try:
        return str(int(segments["segments"].get(key) or 0))
    except Exception:
        return ""


def build_sdr_data(r: dict) -> dict:
    """r — один результат qualify. Повертає значення для полів sdr.html."""
    if not r or r.get("error"):
        return {"domain": (r or {}).get("domain", "")}

    d = {"domain": r.get("domain", ""), "opener": "cold"}

    org = r.get("organic_traffic")
    if org:
        d["org"] = _group(org)
        d["trNow"] = _group(org)

    seg = r.get("segments") or {}
    if seg.get("total"):
        d["top100"] = str(int(seg["total"]))
    if seg.get("segments"):
        d["top3"] = _seg(seg, "top3")
        d["t410"] = _seg(seg, "p4_10")
        d["t1120"] = _seg(seg, "p11_20")
        d["t2150"] = _seg(seg, "p21_50")

    # --- конкуренти + частка в ніші ---
    comps = r.get("competitors") or []
    comps = [c for c in comps if c.get("org_traffic")]
    comps = sorted(comps, key=lambda c: c.get("org_traffic") or 0, reverse=True)[:5]
    our = float(org or 0)
    total = our + sum(float(c.get("org_traffic") or 0) for c in comps)
    if comps:
        lines = []
        for c in comps:
            ot = c.get("org_traffic") or 0
            share = (ot / total * 100) if total else 0
            lines.append(f"{c['domain']} | {_group(ot)} | {_pct(share, dash_zero=False)}")
        d["comps"] = "\n".join(lines)
        top = comps[0]
        d["leader"] = top["domain"]
        if our > 0 and top.get("org_traffic"):
            d["leaderX"] = _num1((top["org_traffic"]) / our)
    if total and our:
        d["orgShare"] = _pct(our / total * 100, dash_zero=False)

    # --- потенціал + воронка ---
    b = r.get("benefit") or {}
    if b.get("queries"):
        d["commKeys"] = str(int(b["queries"]))
    if b.get("multiplier"):
        d["mult"] = _num1(b["multiplier"])
    if b.get("traffic_now") is not None:
        d["trComm"] = _group(b["traffic_now"])
    if b.get("traffic_top1") is not None:
        d["trTop1"] = _group(b["traffic_top1"])
    if b.get("uplift") is not None:
        d["trDelta"] = _group(b["uplift"])
    if b.get("leads_uplift") or b.get("apps_uplift"):
        d["leads"] = _group(b.get("leads_uplift") or b.get("apps_uplift"))
    if b.get("sales_uplift"):
        d["sales"] = _group(b["sales_uplift"])
    if b.get("revenue_uplift"):
        d["rev"] = _group(b["revenue_uplift"])
    if b.get("profit_uplift"):
        d["profit"] = _group(b["profit_uplift"])

    # --- бенчмарки в дужках ---
    parts = []
    if b.get("conv_pct"):
        parts.append(f"конверсія сайту {_num1(b['conv_pct'])}%")
    if b.get("close_pct"):
        parts.append(f"заявка в продаж {_num1(b['close_pct'])}%")
    if b.get("avg_check"):
        parts.append(f"чек {_group(b['avg_check'])} грн")
    if b.get("avg_margin"):
        parts.append(f"маржа ніші {_num1(b['avg_margin'])}%")
    if parts:
        d["bench"] = ", ".join(parts)

    # --- конкретні запити, найближчі до цілі ---
    q = r.get("dotisk_queries") or []
    q = [x for x in q if x.get("keyword")]
    q = sorted(q, key=lambda x: x.get("traffic_top1") or 0, reverse=True)[:8]
    if q:
        lines = []
        for x in q:
            pos = x.get("position") or ""
            lines.append(f"{x['keyword']} | {pos} | "
                         f"{_group(x.get('traffic_now') or 0)} | {_group(x.get('traffic_top1') or 0)}")
        d["queries"] = "\n".join(lines)

    # авто-візуали для листа (замість ручних скрінів)
    try:
        d["visuals"] = build_visuals(r)
    except Exception:
        d["visuals"] = {}

    return d


def build_report_context(r: dict) -> dict:
    """Контекст для серверної PDF-презентації SDR (sdr_report.html) — та сама
    аналітика, що й у листі: трафік, позиції, конкуренти, потенціал/гроші,
    запити, точки зростання."""
    our_org = r.get("organic_traffic") or 0
    our_kw = r.get("organic_keywords") or 0
    seg = r.get("segments") or {}

    comps = [c for c in (r.get("competitors") or []) if c.get("org_traffic")]
    comps = sorted(comps, key=lambda c: c.get("org_traffic") or 0, reverse=True)[:5]
    all_sites = [{"domain": r.get("domain", ""), "organic_traffic": our_org, "is_self": True}]
    for c in comps:
        bx = round((c["org_traffic"] / our_org), 1) if our_org and c["org_traffic"] > our_org else None
        all_sites.append({"domain": c["domain"], "organic_traffic": c["org_traffic"],
                          "is_self": False, "bigger_x": bx})
    all_sites.sort(key=lambda s: s["organic_traffic"], reverse=True)
    max_traffic = max([s["organic_traffic"] for s in all_sites] or [1]) or 1

    q = [x for x in (r.get("dotisk_queries") or []) if x.get("keyword")]
    q = sorted(q, key=lambda x: x.get("traffic_top1") or 0, reverse=True)[:10]

    b = r.get("benefit") or {}
    sgs = seg.get("segments") or {}
    total = seg.get("total") or 0

    # точки зростання (data-driven)
    gp = []
    if sgs.get("p4_10"):
        gp.append(("Дотиснути запити з позицій 4–10 у ТОП-3",
                   f"{_group(sgs['p4_10'])} запитів уже стоять на 4–10 — це найближчий трафік. "
                   "Підсилення цих сторінок (контент, перелінковка, товарні/довірчі сигнали) "
                   "піднімає їх у ТОП-3, де зосереджена основна маса кліків."))
    if sgs.get("p11_20"):
        gp.append(("Витягнути запити з 11–20 на першу сторінку",
                   f"{_group(sgs['p11_20'])} запитів на 11–20 майже не дають трафіку. "
                   "Точкова оптимізація виводить їх у ТОП-10, звідки починаються переходи."))
    if b.get("queries") and b.get("uplift"):
        mult = f" (×{_num1(b['multiplier'])})" if b.get("multiplier") else ""
        gp.append(("Закрити комерційні прогалини",
                   f"{_group(b['queries'])} комерційних запитів у зоні 4–20. Вивід у ТОП-1 додає "
                   f"≈ {_group(b['uplift'])} цільових візитів/міс{mult} — це прямий приріст заявок."))
    if total:
        gp.append(("Нарощувати сторінки, що вже ранжуються",
                   f"Сайт не з нуля: у ТОП-100 вже {_group(total)} ключів. Підсилення наявних "
                   "сторінок дає результат швидше, ніж створення нових з нуля."))
    gp = gp[:4]

    return {
        "domain": r.get("domain", ""),
        "niche": r.get("niche") or {},
        "our": {"organic_traffic": our_org, "organic_keywords": our_kw,
                "segments": {**sgs, "total": total}},
        "all_sites": all_sites,
        "max_traffic": max_traffic,
        "comp_count": len(comps),
        "benefit": b,
        "queries": q,
        "growth": [{"title": t, "detail": dd} for t, dd in gp],
    }


def build_visuals(r: dict) -> dict:
    """HTML-візуали з даних аналізу для вставки у лист замість ручних скрінів:
    графік трафіку + матриця позицій, бари конкурентів, прогноз, таблиця запитів.
    Усе в темній темі (лист на темному тлі). М'яко деградує."""
    vis = {}
    try:
        import charts
    except Exception:
        charts = None

    # matrix: 12-міс графік трафіку + матриця позицій по сегментах
    parts = []
    if charts and r.get("history"):
        try:
            parts.append('<div class="auto-viz">' + charts.traffic_svg(r["history"], theme="dark") + "</div>")
        except Exception:
            pass
    sg = (r.get("segments") or {})
    seg = sg.get("segments") or {}
    tot = sg.get("total") or 0
    if seg and tot:
        labels = [("top3", "ТОП-3"), ("p4_10", "4–10"), ("p11_20", "11–20"),
                  ("p21_50", "21–50"), ("p51_100", "51–100")]
        rows = ""
        for k, lab in labels:
            c = seg.get(k) or 0
            pw = (c / tot * 100) if tot else 0
            rows += ('<div class="mx-row"><span class="mx-l">' + lab + '</span>'
                     '<span class="mx-bar"><i style="width:' + f"{pw:.1f}" + '%"></i></span>'
                     '<span class="mx-n">' + _group(c) + "</span></div>")
        parts.append('<div class="auto-viz mx">' + rows
                     + '<div class="mx-tot">Усього органічних у ТОП-100: <b>' + _group(tot) + "</b></div></div>")
    if parts:
        vis["matrix"] = "".join(parts)

    # comps: бари органічного трафіку (Ви vs конкуренти)
    comps = [c for c in (r.get("competitors") or []) if c.get("org_traffic")]
    comps = sorted(comps, key=lambda c: c.get("org_traffic") or 0, reverse=True)[:5]
    our = r.get("organic_traffic") or 0
    if comps:
        allrows = [(r.get("domain", ""), our, True)] + [(c["domain"], c["org_traffic"], False) for c in comps]
        mx = max([v for _, v, _ in allrows] or [1]) or 1
        rows = ""
        for dom, v, you in sorted(allrows, key=lambda x: x[1], reverse=True):
            w = v / mx * 100 if mx else 0
            rows += ('<div class="cmp-row"><span class="cmp-d' + (" you" if you else "") + '">'
                     + _esc(dom) + (" (Ви)" if you else "") + '</span>'
                     '<span class="cmp-bar"><i class="' + ("you" if you else "") + '" style="width:'
                     + f"{w:.1f}" + '%"></i></span>'
                     '<span class="cmp-n">' + _group(v) + "</span></div>")
        vis["comps"] = '<div class="auto-viz">' + rows + "</div>"

    # potential: прогноз зростання трафіку
    if charts and r.get("history"):
        b = r.get("benefit") or {}
        try:
            fs = charts.forecast_svg(r["history"], b.get("traffic_top1"), theme="dark",
                                     baseline=b.get("traffic_now"))
            vis["potential"] = '<div class="auto-viz">' + fs + "</div>"
        except Exception:
            pass

    # queries: таблиця найближчих до цілі запитів
    q = [x for x in (r.get("dotisk_queries") or []) if x.get("keyword")]
    q = sorted(q, key=lambda x: x.get("traffic_top1") or 0, reverse=True)[:8]
    if q:
        trs = ""
        for x in q:
            trs += ("<tr><td>" + _esc(x["keyword"]) + '</td><td class="c">' + str(x.get("position") or "—")
                    + '</td><td class="c">' + _group(x.get("traffic_now") or 0)
                    + '</td><td class="c hot">' + _group(x.get("traffic_top1") or 0) + "</td></tr>")
        vis["queries"] = ('<div class="auto-viz"><table class="qv"><thead><tr><th>Запит</th>'
                          '<th class="c">Позиція</th><th class="c">Зараз</th><th class="c">У ТОП-1</th>'
                          "</tr></thead><tbody>" + trs + "</tbody></table></div>")
    return vis
