"""Інтеграція з HubSpot: за вебхуком «створено діл» — оцінити домен нашим
алгоритмом і залишити Note на ділі. Працює лише для тестової воронки
(HUBSPOT_TEST_PIPELINE_ID); токен приватного застосунку — у HUBSPOT_TOKEN."""
from __future__ import annotations
import time
import logging
import html as _html
import requests

import config
import qualify

log = logging.getLogger("hubspot-sync")

VERDICT_EMOJI = {"ІДЕАЛЬНО": "🟢", "ДОБРЕ": "🔵", "НЕ ПІДХОДИТЬ": "🔴"}


def _headers():
    return {"Authorization": f"Bearer {config.HUBSPOT_TOKEN}",
            "Content-Type": "application/json"}


def extract_deal_id(data: dict, args: dict) -> str | None:
    keys = ("deal_id", "dealId", "objectId", "hs_object_id", "vid", "id")
    for k in keys:
        v = (args or {}).get(k) or (data.get(k) if isinstance(data, dict) else None)
        if v:
            return str(v)
    props = data.get("properties") if isinstance(data, dict) else None
    if isinstance(props, dict):
        hs = props.get("hs_object_id")
        if isinstance(hs, dict):
            hs = hs.get("value")
        if hs:
            return str(hs)
    return None


def get_deal(deal_id: str) -> dict:
    props = [config.HUBSPOT_DEAL_DOMAIN_PROP, "pipeline", "dealname", "dealstage"]
    url = f"{config.HUBSPOT_API_BASE}/crm/v3/objects/deals/{deal_id}"
    r = requests.get(url, headers=_headers(),
                     params={"properties": ",".join(props)}, timeout=20)
    r.raise_for_status()
    return r.json().get("properties", {}) or {}


def create_note(deal_id: str, note_html: str) -> str:
    url = f"{config.HUBSPOT_API_BASE}/crm/v3/objects/notes"
    body = {"properties": {"hs_note_body": note_html,
                           "hs_timestamp": int(time.time() * 1000)}}
    r = requests.post(url, headers=_headers(), json=body, timeout=20)
    r.raise_for_status()
    note_id = r.json().get("id")
    # прив'язати нотатку до діла (дефолтна асоціація note -> deal)
    assoc = (f"{config.HUBSPOT_API_BASE}/crm/v4/objects/notes/{note_id}"
             f"/associations/default/deals/{deal_id}")
    ra = requests.put(assoc, headers=_headers(), timeout=20)
    ra.raise_for_status()
    return note_id


def update_verdict_prop(deal_id: str, verdict: str):
    if not config.HUBSPOT_VERDICT_PROP:
        return
    url = f"{config.HUBSPOT_API_BASE}/crm/v3/objects/deals/{deal_id}"
    body = {"properties": {config.HUBSPOT_VERDICT_PROP: verdict}}
    requests.patch(url, headers=_headers(), json=body, timeout=20)


def _note_html(domain: str, res: dict) -> str:
    v = res.get("verdict", "?")
    emoji = VERDICT_EMOJI.get(v, "•")
    p = [f"{emoji} <b>SEO-кваліфікація: {v}</b> (бал {res.get('score', '—')})",
         f"Домен: <b>{_html.escape(domain)}</b>"]
    nz = res.get("niche") or {}
    if nz.get("subniche"):
        fit = {True: "підходить", False: "не підходить", None: "не визначено"}.get(nz.get("offer_fit"))
        p.append(f"Ніша: {_html.escape(nz.get('direction_name') or '?')} → "
                 f"{_html.escape(nz.get('industry_name') or '?')} → "
                 f"{_html.escape(nz.get('subniche'))} ({fit} під офер)")
    m = res.get("metrics") or {}
    p.append(f"Комерц. запити 11–30: {m.get('commercial_kw_11_30', '—')} · "
             f"SEO-трафік/міс: {m.get('organic_traffic', '—')}")
    bn = res.get("benefit") or {}
    if bn.get("queries"):
        p.append(f"Потенціал (топ-{bn['queries']}): зараз ~{bn['traffic_now']} → "
                 f"у ТОП-1 ~{bn['traffic_top1']}/міс")
    pd = res.get("paid") or {}
    if pd.get("budget") or pd.get("keywords"):
        b = f"~${pd['budget']}/міс" if pd.get("budget") else "н/д"
        p.append(f"Контекст-бюджет (SemRush): {b} · {pd.get('keywords', 0)} платних запитів")
    ad = res.get("ads") or {}
    if ad.get("checked"):
        p.append("Контекст (Transparency): "
                 + (f"працює, ~{ad.get('count')} оголош." if ad.get("running") else "не знайдено"))
    sc = res.get("social") or {}
    if sc.get("checked") and sc.get("found"):
        p.append(f"Instagram: @{_html.escape(sc.get('handle', ''))} · "
                 f"~{sc.get('followers', '?')} підписн.")
    sv = res.get("services") or []
    if sv:
        mk = {"yes": "✅", "maybe": "🟡", "no": "⛔"}
        svc = "; ".join(f"{mk.get(s['level'], '•')} {s['name']}" for s in sv)
        p.append(f"Послуги: {svc}")
    p.append("<i>Автооцінка — SEO Qualifier</i>")
    return "<br>".join(p)


def process_deal(deal_id: str):
    """Викликається у фоні. Тихо ігнорує діли не з тестової воронки."""
    if not config.HUBSPOT_TOKEN:
        log.warning("HUBSPOT_TOKEN не заданий — пропускаю")
        return
    try:
        props = get_deal(deal_id)
    except Exception:
        log.exception("get_deal failed for %s", deal_id)
        return

    pipeline = props.get("pipeline")
    if config.HUBSPOT_TEST_PIPELINE_ID and pipeline != config.HUBSPOT_TEST_PIPELINE_ID:
        log.info("deal %s pipeline=%s — не тестова, пропуск", deal_id, pipeline)
        return

    domain = (props.get(config.HUBSPOT_DEAL_DOMAIN_PROP) or "").strip()
    if not domain:
        log.info("deal %s — немає домену, пропуск", deal_id)
        try:
            create_note(deal_id, "⚠️ <b>SEO Qualifier:</b> у ділі не заповнене поле Domain — оцінку не виконано.")
        except Exception:
            log.exception("note (no domain) failed for %s", deal_id)
        return

    try:
        res = qualify.qualify(domain, do_onpage=True,
                              do_ads=config.HUBSPOT_ENRICH,
                              do_social=config.HUBSPOT_ENRICH)
    except Exception as e:
        log.exception("qualify failed for %s (%s)", domain, deal_id)
        try:
            create_note(deal_id, f"⚠️ <b>SEO Qualifier:</b> помилка аналізу {_html.escape(domain)} — {_html.escape(str(e)[:150])}")
        except Exception:
            pass
        return

    try:
        create_note(deal_id, _note_html(domain, res))
        update_verdict_prop(deal_id, res.get("verdict", ""))
        log.info("deal %s (%s) -> %s, note created", deal_id, domain, res.get("verdict"))
    except Exception:
        log.exception("create_note failed for %s", deal_id)
