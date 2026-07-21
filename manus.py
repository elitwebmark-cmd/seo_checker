"""Глибока якісна аналітика через Manus API (асинхронно).
Створюємо задачу зі structured_output_schema -> Manus повертає готовий JSON ->
форматуємо у Note. Метрики НЕ вигадуємо: передаємо наші реальні цифри в промпт,
Manus додає якісний аналіз (профіль, конкуренти, SWOT, зачіпки тощо)."""
from __future__ import annotations
import time
import json
import logging
import html as _html
import requests

import config

log = logging.getLogger("manus")

# JSON Schema для структурованого виводу (усі поля -> required, additionalProperties=false)
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["profile", "positioning", "competitors", "gaps_vs_competitors",
                 "site_ux", "site_content", "site_trust", "social", "reputation",
                 "swot", "lead_heat", "service_priority", "call_hooks", "contacts"],
    "properties": {
        "profile": {"type": "string"},
        "positioning": {"type": "string"},
        "competitors": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "note"],
            "properties": {"name": {"type": "string"}, "note": {"type": "string"}}}},
        "gaps_vs_competitors": {"type": "string"},
        "site_ux": {"type": "string"},
        "site_content": {"type": "string"},
        "site_trust": {"type": "string"},
        "social": {"type": "string"},
        "reputation": {"type": "string"},
        "swot": {"type": "object", "additionalProperties": False,
                 "required": ["strengths", "weaknesses", "opportunities", "threats"],
                 "properties": {
                     "strengths": {"type": "array", "items": {"type": "string"}},
                     "weaknesses": {"type": "array", "items": {"type": "string"}},
                     "opportunities": {"type": "array", "items": {"type": "string"}},
                     "threats": {"type": "array", "items": {"type": "string"}}}},
        "lead_heat": {"type": "object", "additionalProperties": False,
                      "required": ["level", "signals"],
                      "properties": {"level": {"type": "string"},
                                     "signals": {"type": "array", "items": {"type": "string"}}}},
        "service_priority": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["service", "why"],
            "properties": {"service": {"type": "string"}, "why": {"type": "string"}}}},
        "call_hooks": {"type": "array", "items": {"type": "string"}},
        "contacts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["role", "name", "linkedin"],
            "properties": {"role": {"type": "string"}, "name": {"type": "string"},
                           "linkedin": {"type": "string"}}}},
    },
}


def _headers():
    return {"x-manus-api-key": config.MANUS_API_KEY, "Content-Type": "application/json"}


def _facts(domain: str, res: dict) -> str:
    m = res.get("metrics") or {}
    nz = res.get("niche") or {}
    bn = res.get("benefit") or {}
    pd = res.get("paid") or {}
    ad = res.get("ads") or {}
    sc = res.get("social") or {}
    lines = [
        f"Домен: {domain}",
        f"Ніша (наш класифікатор): {nz.get('direction_name')} → {nz.get('industry_name')} → {nz.get('subniche')}",
        f"Органічний трафік (SemRush): {m.get('organic_traffic')}/міс",
        f"Комерц. запити у ТОП 11–30: {m.get('commercial_kw_11_30')}",
        f"Потенціал трафіку у ТОП-1 (топ-20 зап.): {bn.get('traffic_top1')}/міс",
        f"Контекст-бюджет (SemRush): ${pd.get('budget')}/міс, платних запитів: {pd.get('keywords')}",
        f"Контекст активний (Transparency): {'так' if ad.get('running') else 'ні/невідомо'}",
        f"Instagram підписників: {sc.get('followers') if sc.get('found') else 'н/д'}",
        f"Наш вердикт кваліфікації: {res.get('verdict')}",
    ]
    return "\n".join(lines)


def _prompt(domain: str, res: dict) -> str:
    return (
        "Ти — старший аналітик SEO/маркетинг-агентства Elit-Web. Проведи глибокий "
        f"якісний аналіз сайту https://{domain} для кваліфікації як потенційного клієнта.\n\n"
        "ВАЖЛИВІ ПРАВИЛА:\n"
        "1) НЕ вигадуй точні метрики (трафік, кількість ключів, DR, бюджет, конверсію). "
        "Кількісні дані бери ЛИШЕ з наданих нижче фактів. Якщо чогось немає — не вигадуй число.\n"
        "2) Конкурентів, оцінку сайту, репутацію, SWOT — аналізуй якісно (переглянь сайт і веб).\n"
        "3) Контакти/ЛПР та рівень 'теплоти' — це ОЦІНКА; імена став лише якщо впевнений, "
        "інакше лишай порожнім. Ми покажемо їх як 'перевірити'.\n"
        "4) Мова відповіді — українська. Стисло й по суті.\n\n"
        "НАШІ ФАКТИ (джерело правди для цифр):\n" + _facts(domain, res) + "\n\n"
        "Заповни структурований результат за схемою: профіль компанії; позиціонування/УТП; "
        "3–5 конкурентів з приміткою хто в чому сильніший; прогалини vs конкуренти; "
        "оцінка сайту (UX, контент, довіра) під конверсію; соцмережі якісно (активність, стиль); "
        "репутація (скарги/похвали); SWOT (S/W/O/T); теплота ліда (level: гарячий/теплий/холодний + "
        "сигнали готовності); пріоритезація послуг (SEO за ТОП / базове SEO / контекст / SMM — що зайде "
        "першим і чому); 3 зачіпки для першого дзвінка; контакти (ролі + LinkedIn, орієнтовно)."
    )


def _deep_find(obj, key):
    """Рекурсивно шукає значення за ключем у вкладеній структурі."""
    if isinstance(obj, dict):
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        for v in obj.values():
            r = _deep_find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find(v, key)
            if r is not None:
                return r
    return None


def create_task(domain: str, res: dict) -> str | None:
    body = {
        "message": {"content": [{"type": "text", "text": _prompt(domain, res)}]},
        "structured_output_schema": SCHEMA,
        "agent_profile": config.MANUS_AGENT_PROFILE,
        "hide_in_task_list": True,
        "interactive_mode": False,
        "locale": "uk",
        "title": f"SEO-кваліфікація: {domain}",
    }
    r = requests.post(f"{config.MANUS_API_BASE}/task.create", headers=_headers(),
                      json=body, timeout=30)
    r.raise_for_status()
    return r.json().get("task_id")


def poll_result(task_id: str) -> dict | None:
    deadline = time.time() + config.MANUS_POLL_TIMEOUT
    url = f"{config.MANUS_API_BASE}/task.listMessages"
    while time.time() < deadline:
        time.sleep(config.MANUS_POLL_INTERVAL)
        try:
            r = requests.get(url, headers=_headers(),
                             params={"task_id": task_id, "order": "desc", "limit": 50}, timeout=30)
            data = r.json()
        except Exception:
            log.exception("manus poll failed")
            continue
        status = _deep_find(data, "agent_status")
        if status == "stopped":
            out = _deep_find(data, "structured_output_result")
            if isinstance(out, str):
                try:
                    out = json.loads(out)
                except Exception:
                    pass
            return out if isinstance(out, dict) else None
        if status == "error":
            log.warning("manus task %s error", task_id)
            return None
    log.warning("manus task %s timeout", task_id)
    return None


def run(domain: str, res: dict) -> dict | None:
    """Синхронний прогін (викликати у фоновому потоці): create -> poll."""
    if not config.MANUS_API_KEY:
        return None
    try:
        task_id = create_task(domain, res)
    except Exception:
        log.exception("manus create failed for %s", domain)
        return None
    if not task_id:
        return None
    return poll_result(task_id)


# ---------- форматування Note ----------
def _bullets(items, sep="<br>", prefix="• "):
    return sep.join(prefix + _html.escape(str(x)) for x in (items or []) if x)


def format_html(domain: str, data: dict) -> str:
    d = data or {}
    sw = d.get("swot") or {}
    heat = d.get("lead_heat") or {}
    comp = "<br>".join(
        f"• <b>{_html.escape(c.get('name', ''))}</b> — {_html.escape(c.get('note', ''))}"
        for c in (d.get("competitors") or []))
    svc = "<br>".join(
        f"• <b>{_html.escape(s.get('service', ''))}</b> — {_html.escape(s.get('why', ''))}"
        for s in (d.get("service_priority") or []))
    contacts = "<br>".join(
        f"• {_html.escape(c.get('role', ''))}: {_html.escape(c.get('name') or '—')}"
        + (f" · <a href=\"{_html.escape(c.get('linkedin'))}\">LinkedIn</a>" if c.get("linkedin") else "")
        for c in (d.get("contacts") or [])) or "—"
    SEP = "——————————"
    p = [
        f"🔎 <b>ГЛИБОКА АНАЛІТИКА (Manus) — {_html.escape(domain)}</b>", "",
        f"<b>Профіль:</b> {_html.escape(d.get('profile', '—'))}",
        f"<b>Позиціонування / УТП:</b> {_html.escape(d.get('positioning', '—'))}",
        SEP,
        "<b>Конкуренти (хто в чому сильніший):</b>", comp or "—",
        f"<b>Прогалини vs конкуренти:</b> {_html.escape(d.get('gaps_vs_competitors', '—'))}",
        SEP,
        f"<b>Сайт · UX:</b> {_html.escape(d.get('site_ux', '—'))}",
        f"<b>Сайт · Контент:</b> {_html.escape(d.get('site_content', '—'))}",
        f"<b>Сайт · Довіра:</b> {_html.escape(d.get('site_trust', '—'))}",
        f"<b>Соцмережі:</b> {_html.escape(d.get('social', '—'))}",
        f"<b>Репутація:</b> {_html.escape(d.get('reputation', '—'))}",
        SEP,
        "<b>SWOT</b>",
        "<b>Сильні:</b><br>" + (_bullets(sw.get("strengths")) or "—"),
        "<b>Слабкі:</b><br>" + (_bullets(sw.get("weaknesses")) or "—"),
        "<b>Можливості:</b><br>" + (_bullets(sw.get("opportunities")) or "—"),
        "<b>Загрози:</b><br>" + (_bullets(sw.get("threats")) or "—"),
        SEP,
        f"<b>🌡️ Теплота ліда:</b> {_html.escape(heat.get('level', '—'))}",
        "<b>Сигнали:</b><br>" + (_bullets(heat.get("signals")) or "—"),
        SEP,
        "<b>Пріоритезація послуг:</b>", svc or "—",
        SEP,
        "<b>Зачіпки для дзвінка:</b><br>" + (_bullets(d.get("call_hooks"), prefix="") or "—"),
        f"<b>Контакти (орієнтовно, перевірити):</b><br>{contacts}",
        "",
        "<i>Джерело: Manus · точні метрики — в основному звіті SEO Qualifier</i>",
    ]
    return "<br>".join(p)


def format_tg(domain: str, data: dict) -> str:
    """Telegram-версія (без таблиць; переноси \\n; підтримує <b>,<a>,<i>)."""
    html = format_html(domain, data)
    return html.replace("<br>", "\n")
