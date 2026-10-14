# -*- coding: utf-8 -*-
"""Мапер даних кваліфікації (результат qualify) у поля конструктора холодної
відписки SDR (sdr.html). Повертає dict {ключ_поля: рядок}, яким JS на сторінці
підставляє значення у форму та рендерить лист + PDF-презентацію.

Ключі збігаються з id/data-k інпутів у sdr.html."""
from __future__ import annotations
import html as _html
import re


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


def _keyword(n) -> str:
    """Відмінок слова «запит» за числом (як keyWord() у листі)."""
    try:
        i = int(n)
    except (TypeError, ValueError):
        return "запитів"
    if not i:
        return "запитів"
    last, two = i % 10, i % 100
    if last == 1 and two != 11:
        return "запит"
    if 2 <= last <= 4 and (two < 12 or two > 14):
        return "запити"
    return "запитів"


def _times_phrase(x) -> str:
    """«майже в N разів» / «у X,Y раза» (як timesPhrase() у листі)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return ""
    if v <= 1.1:
        return ""
    if abs(v - round(v)) > 1e-9:
        return "у " + _num1(v) + " раза"
    i = int(round(v))
    last, two = i % 10, i % 100
    if last == 1 and two != 11:
        w = "раз"
    elif 2 <= last <= 4 and (two < 12 or two > 14):
        w = "рази"
    else:
        w = "разів"
    return f"майже в {i} {w}"


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
    if not org:                      # overview інколи дає 0 — беремо з історії
        hist = r.get("history") or []
        org = (hist[0].get("org_traffic") if hist else 0) or 0
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


def _pint(s) -> int:
    """'2 750' -> 2750, '114 138' -> 114138, '' -> 0 (ігнорує % та текст)."""
    s = str(s or "").replace(" ", " ").replace(" ", " ")
    if "%" in s:
        s = s.split("%")[0]
    digits = "".join(re.findall(r"\d+", s))
    try:
        return int(digits) if digits else 0
    except ValueError:
        return 0


def build_pdf_context(f: dict, niche: dict = None) -> dict:
    """Контекст PDF-презентації SDR зі стану ФОРМИ (ті самі значення й опції, що
    бачить сейлз): відтворює блоки листа слово-в-слово, з урахуванням model/tier
    та будь-яких правок. Конкурентів, сегменти й запити парсить із полів форми."""
    g = lambda k: (f.get(k) or "").strip()
    domain = g("domain")

    # --- конкуренти (бари): свій сайт + рядки з textarea comps ---
    our_org = _pint(g("org"))
    all_sites = []
    if our_org:
        all_sites.append({"domain": domain, "organic_traffic": our_org, "is_self": True})
    for line in g("comps").split("\n"):
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if not parts:
            continue
        dom = parts[0]
        if dom.lower() == domain.lower():
            continue
        all_sites.append({"domain": dom, "organic_traffic": _pint(parts[1] if len(parts) > 1 else 0),
                          "is_self": False})
    all_sites.sort(key=lambda s: s["organic_traffic"], reverse=True)
    max_traffic = max([s["organic_traffic"] for s in all_sites] or [1]) or 1

    # --- матриця позицій зараз ---
    top100 = _pint(g("top100"))
    s3, s410, s1120, s2150 = _pint(g("top3")), _pint(g("t410")), _pint(g("t1120")), _pint(g("t2150"))
    s51 = max(0, top100 - (s3 + s410 + s1120 + s2150))
    seg_rows = []
    if top100:
        for lab, cnt, col in [("ТОП 3", s3, "#159A4B"), ("4–10", s410, "#7DBB3E"),
                              ("11–20", s1120, "#F0A227"), ("21–50", s2150, "#E8720E"),
                              ("51–100", s51, "#FD3A1F")]:
            seg_rows.append({"label": lab, "cnt": cnt, "color": col,
                             "pct": round(cnt / top100 * 100, 1) if top100 else 0})

    # --- запити (таблиця) ---
    queries = []
    for line in g("queries").split("\n"):
        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p != ""]
        if not parts:
            continue
        queries.append({"keyword": parts[0],
                        "position": parts[1] if len(parts) > 1 else "",
                        "now": parts[2] if len(parts) > 2 else "",
                        "top1": parts[3] if len(parts) > 3 else ""})

    leaderX = g("leaderX").replace(",", ".")
    leader_phrase = _times_phrase(leaderX) if leaderX else ""

    return {
        "domain": domain,
        "niche": niche or {},
        # сирі рядки (як у листі, дослівно)
        "org": g("org"), "trWas": g("trWas"), "trNow": g("trNow"),
        "top100": g("top100"), "top3": g("top3"), "t410": g("t410"),
        "t1120": g("t1120"), "t2150": g("t2150"),
        "kw_top100": _keyword(top100),
        "commKeys": g("commKeys"), "kw_comm": _keyword(_pint(g("commKeys"))),
        "mult": g("mult"), "trComm": g("trComm"), "trTop1": g("trTop1"), "trDelta": g("trDelta"),
        "leads": g("leads"), "sales": g("sales"), "rev": g("rev"), "profit": g("profit"),
        "bench": g("bench"),
        "leader": g("leader"), "leader_phrase": leader_phrase,
        "model": g("model") or "keys",
        "tier": g("tier") or "std",
        # дані для візуалів
        "all_sites": all_sites, "max_traffic": max_traffic,
        "seg_rows": seg_rows, "top100_n": top100,
        "queries": queries,
    }


def fields_from_result(r: dict) -> dict:
    """Поля форми за замовчуванням із результату аналізу (для GET без форми)."""
    d = build_sdr_data(r)
    d.pop("visuals", None)
    d.setdefault("model", "keys")
    d.setdefault("tier", "std")
    return d


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
