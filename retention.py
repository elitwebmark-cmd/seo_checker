# -*- coding: utf-8 -*-
"""Retention-маркетинг: моделювання LTV та потенціалу утримання + реальні
сигнали каналів із сайту. Зовнішніх API не потребує — рахується завжди.

Логіка: беремо економіку ніші (чек, маржа, конверсії) + нішеві retention-
бенчмарки (repeat-rate, частота, строк життя) -> LTV, upside від утримання,
owned-audience, рекомендовані канали, quick wins."""
from __future__ import annotations
import config
import niche


def _num(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def build(niche_info: dict, benefit: dict, overview: dict,
          onp: dict, social_info: dict) -> dict:
    ni = niche_info or {}
    check = _num(ni.get("avg_check"))
    margin = _num(ni.get("avg_margin"))
    if check <= 0 or margin <= 0:
        return None   # без економіки ніші моделювати нема сенсу

    repeat_rate, freq, life_m = niche.retention_bench(ni)
    years = max(life_m / 12.0, 0.1)
    orders_ltv = max(freq * years, 1.0)          # покупок за життя клієнта
    ltv_rev = check * orders_ltv
    ltv_profit = ltv_rev * margin / 100.0
    first_profit = check * margin / 100.0
    upside = max(ltv_profit - first_profit, 0)   # прибуток понад першу покупку

    # поточні нові клієнти/міс (з трафіку та конверсій)
    traffic = _num((benefit or {}).get("traffic_now")) or _num((overview or {}).get("organic_traffic"))
    conv_f = _num(ni.get("conv_pct")) / 100.0
    close_f = (_num(ni.get("close_pct")) / 100.0) if ni.get("close_pct") else 1.0
    monthly_customers = int(round(traffic * conv_f * close_f)) if traffic else 0
    annual_customers = monthly_customers * 12

    # Консервативна оцінка потенціалу програми: з поточного потоку клієнтів
    # retention-програма повертає додатково uplift% від нішевого repeat-rate,
    # кожне повернення = ще одне замовлення з прибутком першої покупки.
    uplift = config.RETENTION_PROGRAM_UPLIFT
    monthly_extra = int(round(monthly_customers * first_profit * (repeat_rate / 100.0) * uplift))
    annual_extra = monthly_extra * 12

    # owned-audience інвентар
    ig = None
    if social_info and social_info.get("found") and social_info.get("followers") is not None:
        ig = int(_num(social_info.get("followers")))
    audience = {"ig_followers": ig, "monthly_traffic": int(traffic) if traffic else 0}

    # сигнали каналів із сайту
    sig = (onp or {}).get("retention_signals") if onp else None
    signals = None
    if sig:
        signals = [
            {"name": "Захоплення email / розсилка", "present": bool(sig.get("email_capture"))},
            {"name": "Онлайн-чат / месенджер", "present": bool(sig.get("chat"))},
            {"name": "Програма лояльності / бонуси", "present": bool(sig.get("loyalty"))},
            {"name": "Мобільний застосунок", "present": bool(sig.get("app"))},
            {"name": "Блог / контент для nurturing", "present": bool(sig.get("blog"))},
        ]

    # рекомендовані канали (нішеві нюанси)
    channels = [
        "Email-флоу: welcome, кинутий кошик, пост-продаж, реактивація (win-back)",
        "Telegram / Viber-розсилки та бот для повторних продажів",
        "Ретаргетинг на власну базу (Google/Meta) — догрів і крос-сейл",
    ]
    if freq >= 3:
        channels.append("Програма лояльності / бонуси (висока частота покупок у ніші)")
    if freq >= 6:
        channels.append("Push-сповіщення (web/app) під часті покупки")
    if (ni.get("conv_type") or "").startswith("Лід"):
        channels.append("CRM-нуртуринг лідів: серії листів до угоди + після неї")

    # quick wins із сигналів
    wins = []
    if sig:
        if not sig.get("email_capture"):
            wins.append("Немає захоплення email на сайті — втрачається база для розсилок")
        if not sig.get("chat"):
            wins.append("Немає онлайн-чату/месенджера — нижча повторна залученість і підтримка")
        if freq >= 3 and not sig.get("loyalty"):
            wins.append("Висока частота покупок у ніші, але немає програми лояльності")
        if ig and ig >= config.SMM_FOLLOWERS_MIN and not sig.get("email_capture"):
            wins.append(f"Велика IG-аудиторія (~{ig}) не конвертується у власну email-базу")
        if not sig.get("blog"):
            wins.append("Немає блогу — бракує контенту для nurturing та утримання")
    if not wins:
        wins.append("Базові канали утримання є — фокус на якості сценаріїв і сегментації")

    return {
        "checked": True,
        "repeat_rate": repeat_rate,          # % повторних (бенчмарк ніші)
        "freq": round(freq, 1),              # покупок/рік
        "life_months": life_m,               # строк життя клієнта
        "ltv_revenue": int(round(ltv_rev)),
        "ltv_profit": int(round(ltv_profit)),
        "first_profit": int(round(first_profit)),
        "upside_per_customer": int(round(upside)),
        "monthly_customers": monthly_customers,
        "monthly_extra_profit": monthly_extra,
        "annual_extra_profit": annual_extra,
        "uplift_pct": int(round(uplift * 100)),
        "audience": audience,
        "signals": signals,
        "channels": channels,
        "quick_wins": wins,
    }
