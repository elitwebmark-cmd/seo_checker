# -*- coding: utf-8 -*-
"""Мапер даних кваліфікації (результат qualify) у поля конструктора холодної
відписки SDR (sdr.html). Повертає dict {ключ_поля: рядок}, яким JS на сторінці
підставляє значення у форму та рендерить лист + PDF-презентацію.

Ключі збігаються з id/data-k інпутів у sdr.html."""
from __future__ import annotations


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

    return d
