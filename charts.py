"""Генерація простих inline-SVG графіків для веб-результатів (без залежностей).
Тема elitweb: --red #FD3A1F, --gold #FFC85A, --mute #8C8C95, --bord #2A2A31."""
from __future__ import annotations
from typing import List, Dict, Any

RED = "#FD3A1F"
GOLD = "#FFC85A"
MUTE = "#8C8C95"
MUTE2 = "#C4C4CC"
BORD = "#2A2A31"
GRID = "#23232A"
BG = "#0E0E12"


def _fmt(n: int) -> str:
    n = int(round(n or 0))
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1000:.1f}k".replace(".0k", "k")
    return str(n)


def _month_label(ym: str) -> str:
    ym = str(ym or "")
    if len(ym) >= 6:
        return f"{ym[4:6]}.{ym[2:4]}"   # MM.YY
    return ym or "—"


_THEMES = {
    "dark":  {"line": RED, "area": RED, "grid": GRID, "axis": MUTE,
              "dot": RED, "last": GOLD, "dotstroke": BG, "val": GOLD,
              "fc": "#28C76F", "fcval": "#28C76F"},
    "light": {"line": "#FD3A1F", "area": "#FD3A1F", "grid": "#E6E6EA", "axis": "#9A9AA2",
              "dot": "#FD3A1F", "last": "#C12814", "dotstroke": "#FFFFFF", "val": "#C12814",
              "fc": "#159A4B", "fcval": "#159A4B"},
}

# Крива виходу трафіку в ціль по місяцях (кумулятивна частка приросту).
FORECAST_CURVE = [0.10, 0.30, 0.80, 1.00]


def _add_months(ym: str, k: int) -> str:
    ym = str(ym or "")
    if len(ym) < 6:
        return ym
    y, m = int(ym[:4]), int(ym[4:6])
    m += k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}{m:02d}"


def traffic_svg(history: List[Dict[str, Any]], months: int = 12, theme: str = "dark",
                forecast_target: int = None) -> str:
    """Лінійний графік органічного трафіку по місяцях (найстаріший ліворуч).
    history — список dict {date:'YYYYMM', org_traffic, ...} (свіжі першими).
    forecast_target — якщо задано і > поточного, домальовує пунктирне продовження
    на 4 майбутні місяці до цільового трафіку (крива FORECAST_CURVE)."""
    if not history:
        return ""
    T = _THEMES.get(theme, _THEMES["dark"])
    pts = list(reversed(history))[-months:]           # oldest -> newest
    pts = [p for p in pts if p.get("date")]
    vals = [max(0, int(p.get("org_traffic", 0) or 0)) for p in pts]
    if len(vals) < 2 or max(vals) <= 0:
        return ""

    n = len(vals)
    last_v = vals[-1]

    # --- прогнозні точки (майбутні місяці) ---
    fvals, flabels = [], []
    tgt = int(forecast_target or 0)
    if tgt and tgt > last_v:
        base = last_v
        gap = tgt - base
        last_date = pts[-1].get("date")
        for j, cf in enumerate(FORECAST_CURVE, start=1):
            fvals.append(int(round(base + gap * cf)))
            flabels.append(_add_months(last_date, j))

    W, H = 760, 230
    padL, padR, padT, padB = 56, 16, 16, 34
    plotW = W - padL - padR
    plotH = H - padT - padB
    total = n + len(fvals)
    vmax = max(max(vals), tgt if fvals else 0)
    import math
    step = 10 ** max(0, len(str(int(vmax))) - 2)
    top = math.ceil(vmax / step) * step if step else vmax
    top = max(top, 1)

    def X(i): return padL + (plotW * i / (total - 1))
    def Y(v): return padT + plotH * (1 - v / top)

    # сітка + підписи осі Y
    grid = []
    for gv in (0, top / 2, top):
        y = Y(gv)
        grid.append(f'<line x1="{padL}" y1="{y:.1f}" x2="{W-padR}" y2="{y:.1f}" '
                    f'stroke="{T["grid"]}" stroke-width="1"/>')
        grid.append(f'<text x="{padL-8}" y="{y+4:.1f}" text-anchor="end" '
                    f'fill="{T["axis"]}" font-size="11" font-weight="700">{_fmt(gv)}</text>')

    # фактична лінія
    line_pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    area = (f"M {X(0):.1f},{Y(0):.1f} "
            + " ".join(f"L {X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
            + f" L {X(n-1):.1f},{Y(0):.1f} Z")

    dots, xlabels = [], []
    for i, (p, v) in enumerate(zip(pts, vals)):
        cx, cy = X(i), Y(v)
        last = (i == n - 1)
        r = 4 if last else 2.6
        col = T["last"] if last else T["dot"]
        dots.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{col}" '
                    f'stroke="{T["dotstroke"]}" stroke-width="1.5"/>')
        xlabels.append(f'<text x="{cx:.1f}" y="{H-12}" text-anchor="middle" '
                       f'fill="{T["axis"]}" font-size="10.5" font-weight="700">'
                       f'{_month_label(p.get("date"))}</text>')

    fc_svg = ""
    if fvals:
        # пунктирна лінія від останньої фактичної точки через прогнозні
        fc_pts = [(X(n - 1), Y(last_v))] + [(X(n + j), Y(fv)) for j, fv in enumerate(fvals)]
        fc_poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in fc_pts)
        divx = (X(n - 1) + X(n)) / 2
        fc_parts = [
            f'<line x1="{divx:.1f}" y1="{padT}" x2="{divx:.1f}" y2="{padT+plotH:.1f}" '
            f'stroke="{T["grid"]}" stroke-width="1" stroke-dasharray="2 3"/>',
            f'<polyline points="{fc_poly}" fill="none" stroke="{T["fc"]}" '
            f'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round" '
            f'stroke-dasharray="6 4"/>',
        ]
        for j, fv in enumerate(fvals):
            cx, cy = X(n + j), Y(fv)
            last = (j == len(fvals) - 1)
            r = 4.5 if last else 3
            fc_parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" '
                f'fill="{T["fc"] if last else T["dotstroke"]}" '
                f'stroke="{T["fc"]}" stroke-width="1.8"/>')
            fc_parts.append(
                f'<text x="{cx:.1f}" y="{H-12}" text-anchor="middle" '
                f'fill="{T["fc"]}" font-size="10.5" font-weight="700">'
                f'{_month_label(flabels[j])}</text>')
        # значення цілі біля останньої прогнозної точки
        tx, ty = X(total - 1), Y(fvals[-1])
        tlbl_y = ty - 10 if ty > padT + 16 else ty + 16
        fc_parts.append(
            f'<text x="{tx:.1f}" y="{tlbl_y:.1f}" text-anchor="end" '
            f'fill="{T["fcval"]}" font-size="13" font-weight="800">{_fmt(fvals[-1])}</text>')
        fc_parts.append(
            f'<text x="{X(n):.1f}" y="{padT+11:.1f}" text-anchor="start" '
            f'fill="{T["fc"]}" font-size="10" font-weight="800" '
            f'letter-spacing="0.5">ПРОГНОЗ · 4 МІС</text>')
        fc_svg = "".join(fc_parts)

    # значення останньої фактичної точки
    lx, lv = X(n - 1), last_v
    ly = Y(lv)
    lbl_y = ly - 10 if ly > padT + 16 else ly + 16
    val_lbl = (f'<text x="{lx:.1f}" y="{lbl_y:.1f}" text-anchor="middle" '
               f'fill="{T["val"]}" font-size="12.5" font-weight="800">{_fmt(lv)}</text>')

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="Динаміка органічного трафіку">'
        f'<defs><linearGradient id="tgrad" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{T["area"]}" stop-opacity="0.22"/>'
        f'<stop offset="1" stop-color="{T["area"]}" stop-opacity="0"/></linearGradient></defs>'
        + "".join(grid)
        + f'<path d="{area}" fill="url(#tgrad)"/>'
        + f'<polyline points="{line_pts}" fill="none" stroke="{T["line"]}" '
          f'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
        + "".join(dots) + fc_svg + "".join(xlabels) + val_lbl
        + "</svg>"
    )


def forecast_svg(history: List[Dict[str, Any]], target: int, theme: str = "dark",
                 actual_months: int = 3, gradient_id: str = "fgrad") -> str:
    """Компактний графік прогнозу зростання: останні `actual_months` фактичних
    місяців + 4 прогнозовані (крива FORECAST_CURVE) до цільового трафіку `target`.
    Для правої колонки блоку «Потенціал». Порожньо, якщо ціль не вища за поточний."""
    if not history:
        return ""
    T = _THEMES.get(theme, _THEMES["dark"])
    pts = list(reversed(history))[-actual_months:]
    pts = [p for p in pts if p.get("date")]
    vals = [max(0, int(p.get("org_traffic", 0) or 0)) for p in pts]
    if len(vals) < 1 or max(vals) <= 0:
        return ""
    tgt = int(target or 0)
    last_v = vals[-1]
    if not tgt or tgt <= last_v:
        return ""

    base, gap = last_v, tgt - last_v
    last_date = pts[-1].get("date")
    fvals = [int(round(base + gap * cf)) for cf in FORECAST_CURVE]
    flabels = [_add_months(last_date, j) for j in range(1, len(FORECAST_CURVE) + 1)]

    na = len(vals)
    total = na + len(fvals)
    W, H = 360, 210
    padL, padR, padT, padB = 42, 34, 26, 34
    plotW, plotH = W - padL - padR, H - padT - padB
    vmax = max(max(vals), tgt)
    import math
    step = 10 ** max(0, len(str(int(vmax))) - 2)
    top = math.ceil(vmax / step) * step if step else vmax
    # запас зверху, щоб підпис цілі не налазив на верхню точку
    if step and tgt > 0.88 * top:
        top += step
    top = max(top, 1)

    def X(i): return padL + (plotW * i / (total - 1))
    def Y(v): return padT + plotH * (1 - v / top)

    parts = [
        f'<defs><linearGradient id="{gradient_id}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{T["fc"]}" stop-opacity="0.20"/>'
        f'<stop offset="1" stop-color="{T["fc"]}" stop-opacity="0"/></linearGradient></defs>'
    ]
    for gv in (0, top / 2, top):
        y = Y(gv)
        parts.append(f'<line x1="{padL}" y1="{y:.1f}" x2="{W-padR}" y2="{y:.1f}" '
                     f'stroke="{T["grid"]}" stroke-width="1"/>')
        parts.append(f'<text x="{padL-6}" y="{y+3.5:.1f}" text-anchor="end" '
                     f'fill="{T["axis"]}" font-size="10" font-weight="700">{_fmt(gv)}</text>')
    # роздільник факт|прогноз
    divx = (X(na - 1) + X(na)) / 2
    parts.append(f'<line x1="{divx:.1f}" y1="{padT}" x2="{divx:.1f}" y2="{padT+plotH:.1f}" '
                 f'stroke="{T["grid"]}" stroke-width="1" stroke-dasharray="2 3"/>')
    # фактична лінія
    act_poly = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    parts.append(f'<polyline points="{act_poly}" fill="none" stroke="{T["line"]}" '
                 f'stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>')
    for i, v in enumerate(vals):
        last = (i == na - 1)
        parts.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{4 if last else 3}" '
                     f'fill="{T["last"] if last else T["dot"]}" '
                     f'stroke="{T["dotstroke"]}" stroke-width="1.5"/>')
    ly = Y(last_v)
    parts.append(f'<text x="{X(na-1):.1f}" y="{(ly-8 if ly>padT+14 else ly+15):.1f}" '
                 f'text-anchor="middle" fill="{T["val"]}" font-size="11" '
                 f'font-weight="800">{_fmt(last_v)}</text>')
    # прогнозна область + пунктирна лінія
    fc_pts = [(X(na - 1), Y(last_v))] + [(X(na + j), Y(fv)) for j, fv in enumerate(fvals)]
    fc_poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in fc_pts)
    area = (f"M {fc_pts[0][0]:.1f},{Y(0):.1f} "
            + " ".join(f"L {x:.1f},{y:.1f}" for x, y in fc_pts)
            + f" L {fc_pts[-1][0]:.1f},{Y(0):.1f} Z")
    parts.append(f'<path d="{area}" fill="url(#{gradient_id})"/>')
    parts.append(f'<polyline points="{fc_poly}" fill="none" stroke="{T["fc"]}" '
                 f'stroke-width="2.6" stroke-dasharray="6 4" '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')
    for j, fv in enumerate(fvals):
        last = (j == len(fvals) - 1)
        parts.append(f'<circle cx="{X(na+j):.1f}" cy="{Y(fv):.1f}" r="{5 if last else 3}" '
                     f'fill="{T["fc"] if last else T["dotstroke"]}" '
                     f'stroke="{T["fc"]}" stroke-width="1.8"/>')
    ty = Y(fvals[-1])
    parts.append(f'<text x="{X(total-1):.1f}" y="{(ty-12 if ty>padT+20 else ty+20):.1f}" '
                 f'text-anchor="middle" fill="{T["fcval"]}" font-size="11.5" '
                 f'font-weight="800">{_fmt(fvals[-1])}</text>')
    parts.append(f'<text x="{X(na):.1f}" y="{padT-8:.1f}" text-anchor="start" '
                 f'fill="{T["fc"]}" font-size="9" font-weight="800" '
                 f'letter-spacing="0.5">ПРОГНОЗ · 4 МІС</text>')
    # підписи X
    for i, p in enumerate(pts):
        parts.append(f'<text x="{X(i):.1f}" y="{H-12}" text-anchor="middle" '
                     f'fill="{T["axis"]}" font-size="9.5" font-weight="700">'
                     f'{_month_label(p.get("date"))}</text>')
    for j, lb in enumerate(flabels):
        mm = str(lb)[4:6] if len(str(lb)) >= 6 else str(lb)
        parts.append(f'<text x="{X(na+j):.1f}" y="{H-12}" text-anchor="middle" '
                     f'fill="{T["fc"]}" font-size="9.5" font-weight="700">{mm}</text>')

    return (f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" '
            f'role="img" aria-label="Прогноз зростання трафіку">'
            + "".join(parts) + "</svg>")
