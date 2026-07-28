# -*- coding: utf-8 -*-
"""Генерація брендованого PDF-звіту (темна тема Elit-Web, клієнтський вигляд).
Рендер: Jinja report.html -> WeasyPrint. WeasyPrint імпортується ліниво,
щоб відсутність системних бібліотек не валила застосунок."""
from __future__ import annotations
import os
import base64
import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

_DIR = os.path.dirname(os.path.abspath(__file__))
_env = Environment(loader=FileSystemLoader(_DIR),
                   autoescape=select_autoescape(["html"]))


def _sp(n) -> str:
    try:
        return f"{int(round(float(n))):,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(n if n is not None else "—")


_env.filters["sp"] = _sp

_LOGO_CACHE = None


def _logo_data_uri() -> str:
    global _LOGO_CACHE
    if _LOGO_CACHE is None:
        path = os.path.join(_DIR, "static", "logo.png")
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            _LOGO_CACHE = f"data:image/png;base64,{b64}"
        except OSError:
            _LOGO_CACHE = ""
    return _LOGO_CACHE


def render_html(res: dict) -> str:
    import charts
    hist = res.get("history") or []
    chart_svg = charts.traffic_svg(hist, theme="light")
    forecast_svg = charts.forecast_svg(
        hist, (res.get("benefit") or {}).get("traffic_top1"), theme="light")
    nt = res.get("niche_trend") or {}
    trend_svg = charts.trend_svg(nt.get("points"), theme="light") if nt.get("points") else ""
    return _env.get_template("report.html").render(
        r=res,
        logo=_logo_data_uri(),
        chart_svg=chart_svg,
        forecast_svg=forecast_svg,
        trend_svg=trend_svg,
        today=datetime.date.today().strftime("%d.%m.%Y"),
    )


def build(res: dict) -> bytes:
    """Повертає PDF-байти звіту по домену. Кидає виняток, якщо рушій недоступний."""
    from weasyprint import HTML   # ліниво: потребує системних бібліотек
    html = render_html(res)
    return HTML(string=html, base_url=_DIR).write_pdf()
