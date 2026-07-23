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


def traffic_svg(history: List[Dict[str, Any]], months: int = 12) -> str:
    """Лінійний графік органічного трафіку по місяцях (найстаріший ліворуч).
    history — список dict {date:'YYYYMM', org_traffic, ...} (свіжі першими)."""
    if not history:
        return ""
    pts = list(reversed(history))[-months:]           # oldest -> newest
    pts = [p for p in pts if p.get("date")]
    vals = [max(0, int(p.get("org_traffic", 0) or 0)) for p in pts]
    if len(vals) < 2 or max(vals) <= 0:
        return ""

    W, H = 760, 230
    padL, padR, padT, padB = 56, 16, 16, 34
    plotW = W - padL - padR
    plotH = H - padT - padB
    n = len(vals)
    vmax = max(vals)
    # приємна верхня межа
    import math
    step = 10 ** max(0, len(str(int(vmax))) - 2)
    top = math.ceil(vmax / step) * step if step else vmax
    top = max(top, 1)

    def X(i): return padL + (plotW * i / (n - 1))
    def Y(v): return padT + plotH * (1 - v / top)

    # горизонтальні лінії сітки + підписи осі Y (0, half, top)
    grid = []
    for gv in (0, top / 2, top):
        y = Y(gv)
        grid.append(f'<line x1="{padL}" y1="{y:.1f}" x2="{W-padR}" y2="{y:.1f}" '
                    f'stroke="{GRID}" stroke-width="1"/>')
        grid.append(f'<text x="{padL-8}" y="{y+4:.1f}" text-anchor="end" '
                    f'fill="{MUTE}" font-size="11" font-weight="700">{_fmt(gv)}</text>')

    line_pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    area = (f"M {X(0):.1f},{Y(0):.1f} "
            + " ".join(f"L {X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
            + f" L {X(n-1):.1f},{Y(0):.1f} Z")

    dots, xlabels = [], []
    for i, (p, v) in enumerate(zip(pts, vals)):
        cx, cy = X(i), Y(v)
        last = (i == n - 1)
        r = 4 if last else 2.6
        col = GOLD if last else RED
        dots.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{col}" '
                    f'stroke="{BG}" stroke-width="1.5"/>')
        xlabels.append(f'<text x="{cx:.1f}" y="{H-12}" text-anchor="middle" '
                       f'fill="{MUTE}" font-size="10.5" font-weight="700">'
                       f'{_month_label(p.get("date"))}</text>')
    # значення останньої точки
    lx, lv = X(n-1), vals[-1]
    ly = Y(lv)
    lbl_y = ly - 10 if ly > padT + 16 else ly + 16
    val_lbl = (f'<text x="{lx:.1f}" y="{lbl_y:.1f}" text-anchor="end" '
               f'fill="{GOLD}" font-size="12.5" font-weight="800">{_fmt(lv)}</text>')

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="Динаміка органічного трафіку">'
        f'<defs><linearGradient id="tgrad" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{RED}" stop-opacity="0.34"/>'
        f'<stop offset="1" stop-color="{RED}" stop-opacity="0"/></linearGradient></defs>'
        + "".join(grid)
        + f'<path d="{area}" fill="url(#tgrad)"/>'
        + f'<polyline points="{line_pts}" fill="none" stroke="{RED}" '
          f'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
        + "".join(dots) + "".join(xlabels) + val_lbl
        + "</svg>"
    )
