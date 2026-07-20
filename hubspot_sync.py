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
    # Створюємо нотатку одразу з асоціацією до діла (атомарно, без окремого PUT)
    url = f"{config.HUBSPOT_API_BASE}/crm/v3/objects/notes"
    body = {
        "properties": {"hs_note_body": note_html,
                       "hs_timestamp": int(time.time() * 1000)},
        "associations": [{
            "to": {"id": str(deal_id)},
            "types": [{"associationCategory": "HUBSPOT_DEFINED",
                       "associationTypeId": config.HUBSPOT_NOTE_DEAL_ASSOC_ID}],
        }],
    }
    r = requests.post(url, headers=_headers(), json=body, timeout=20)
    r.raise_for_status()
    return r.json().get("id")


def update_verdict_prop(deal_id: str, verdict: str):
    if not config.HUBSPOT_VERDICT_PROP:
        return
    url = f"{config.HUBSPOT_API_BASE}/crm/v3/objects/deals/{deal_id}"
    body = {"properties": {config.HUBSPOT_VERDICT_PROP: verdict}}
    requests.patch(url, headers=_headers(), json=body, timeout=20)


SEP = "——————————"


def _fmt(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(n)


def _ym(d: str) -> str:
    d = str(d or "")
    return f"{d[:4]}-{d[4:6]}" if len(d) >= 6 else (d or "—")


def _hist_seo(hist) -> str:
    if not hist:
        return "н/д"
    return "<br>".join(
        f"{_ym(h.get('date'))}: трафік {_fmt(h.get('org_traffic', 0))} · ключів {_fmt(h.get('org_kw', 0))}"
        for h in hist[:10])


def _hist_ppc(hist) -> str:
    if not hist:
        return "н/д"
    return "<br>".join(
        f"{_ym(h.get('date'))}: ключів {_fmt(h.get('ad_kw', 0))} · трафік {_fmt(h.get('ad_traffic', 0))} · ${_fmt(h.get('ad_cost', 0))}"
        for h in hist[:10])


def _seo_conclusion(res) -> str:
    v = res.get("verdict"); m = res.get("metrics") or {}; nz = res.get("niche") or {}
    pos = m.get("commercial_kw_11_30", 0); traf = m.get("organic_traffic", 0)
    if nz.get("offer_fit") is False:
        return "Ніша не підходить під офер SEO за ТОП."
    if v in ("ІДЕАЛЬНО", "ДОБРЕ"):
        return (f"Сильний кандидат: {pos} комерц. запитів у ТОП 11–30, "
                f"трафік {_fmt(traf)}/міс, є потенціал зростання.")
    if traf < config.GROWTH_TRAFFIC_MIN:
        return f"Замало трафіку/потенціалу ({_fmt(traf)}/міс, треба >{_fmt(config.GROWTH_TRAFFIC_MIN)})."
    if pos < config.COMMERCIAL_KW_MIN:
        return f"Мало комерційних запитів у ТОП 11–30 ({pos}, треба {config.COMMERCIAL_KW_MIN}+)."
    return "Не проходить за нашими порогами під офер."


def _ppc_conclusion(res) -> str:
    ad = res.get("ads") or {}; pd = res.get("paid") or {}; m = res.get("metrics") or {}
    budget = pd.get("budget", 0); pk = pd.get("keywords", 0)
    comm = m.get("commercial_kw_11_30", 0)
    if ad.get("running"):
        b = f"~${_fmt(budget)}/міс, {pk} запитів" if budget else "бюджет SemRush не оцінив"
        return f"Уже інвестує в контекст ({b}) — є бюджет і намір; можна вести/оптимізувати."
    if comm >= 50 or pk > 0:
        return "Комерційна семантика є — контекст доречний для запуску."
    return "Слабкий потенціал під контекст (мало комерційних запитів)."


def _smm_conclusion(res) -> str:
    sc = res.get("social") or {}
    if not sc.get("checked"):
        return "не перевірялось"
    if not sc.get("found"):
        return "Профіль Instagram на сайті не знайдено — потенціал з нуля."
    f = sc.get("followers") or 0
    if sc.get("is_private"):
        return f"Профіль приватний (~{_fmt(f)} підписн.) — оцінка обмежена."
    base = f"~{_fmt(f)} підписн., залученість ~{sc.get('avg_engagement', 0)}/пост"
    if f >= config.SMM_FOLLOWERS_MIN:
        return f"Є аудиторія ({base}) — SMM/таргет доречні."
    return f"Профіль слабкий ({base}) — треба розвивати."


def find_duplicate_deals(domain: str, exclude_id: str):
    """Інші угоди з тим самим доменом у HubSpot. None = перевірка не вдалася."""
    try:
        url = f"{config.HUBSPOT_API_BASE}/crm/v3/objects/deals/search"
        body = {"filterGroups": [{"filters": [
            {"propertyName": config.HUBSPOT_DEAL_DOMAIN_PROP, "operator": "EQ", "value": domain}]}],
            "properties": ["dealname"], "limit": 20}
        r = requests.post(url, headers=_headers(), json=body, timeout=20)
        if r.status_code != 200:
            return None
        rows = r.json().get("results", [])
        return [d for d in rows if str(d.get("id")) != str(exclude_id)]
    except Exception:
        return None


def _note_html(domain: str, res: dict, dups=None) -> str:
    v = res.get("verdict", "?")
    emoji = VERDICT_EMOJI.get(v, "•")
    m = res.get("metrics") or {}; nz = res.get("niche") or {}; bn = res.get("benefit") or {}
    pd = res.get("paid") or {}; ad = res.get("ads") or {}; sc = res.get("social") or {}
    hist = res.get("history") or []

    niche_line = (f"{nz.get('direction_name') or '?'} → {nz.get('industry_name') or '?'} → {nz.get('subniche')}"
                  if nz.get("subniche") else "не визначено")
    if dups is None:
        dup_txt = "перевірка недоступна"
    elif not dups:
        dup_txt = "не знайдено"
    else:
        dup_txt = f"знайдено {len(dups)} угод(и) з цим доменом"

    ads_line = ((f"працює, ~{ad.get('count')} оголош." if ad.get("running") else "не знайдено")
                if ad.get("checked") else "не перевірялось")
    budget_line = (f"~${_fmt(pd.get('budget'))}/міс · {pd.get('keywords', 0)} платних запитів"
                   if (pd.get("budget") or pd.get("keywords")) else "н/д")

    if sc.get("checked") and sc.get("found"):
        ig_line = f"@{_html.escape(sc.get('handle', ''))} · ~{_fmt(sc.get('followers') or 0)} підписн."
        reg_line = (f"залученість ~{sc.get('avg_engagement', 0)}/пост · "
                    f"{'активний' if sc.get('active') else 'активність низька'} (дати постів недоступні)")
    elif sc.get("checked"):
        ig_line, reg_line = "профіль на сайті не знайдено", "—"
    else:
        ig_line, reg_line = "не перевірялось", "—"

    mk = {"yes": "✅", "maybe": "🟡", "no": "⛔"}
    svc = "<br>".join(f"{mk.get(s['level'], '•')} {_html.escape(s['name'])}" for s in (res.get("services") or []))

    p = [
        f"{emoji} <b>SEO-кваліфікація: {v}</b> (бал {res.get('score', '—')})", "",
        "<b>ЗАГАЛЬНА ІНФОРМАЦІЯ</b>",
        f"Домен: <b>{_html.escape(domain)}</b>",
        f"Ніша: {_html.escape(niche_line)}",
        "Підрядник: —",
        f"Дублі в ЦРМ: {dup_txt}",
        SEP, "",
        "<b>SEO ІНФОРМАЦІЯ</b>",
        f"Пошуковий трафік зараз: {_fmt(m.get('organic_traffic', 0))}/міс",
        "Динаміка пошукового (10 міс.):",
        _hist_seo(hist),
        f"Комерц. запити ТОП 11–30: {m.get('commercial_kw_11_30', 0)} шт",
        f"Трафік цих запитів: ~{_fmt(bn.get('traffic_now', 0))} відвідувачів/міс",
        f"Потенційний трафік (ТОП-1): ~{_fmt(bn.get('traffic_top1', 0))}/міс",
        f"Висновок по SEO: {_seo_conclusion(res)}",
        SEP, "",
        "<b>PPC ІНФОРМАЦІЯ</b>",
        f"Контекст (Transparency): {ads_line}",
        f"Контекст-бюджет (SemRush): {budget_line}",
        "Динаміка PPC (10 міс.):",
        _hist_ppc(hist),
        f"Висновок по PPC: {_ppc_conclusion(res)}",
        SEP, "",
        "<b>SMM ІНФОРМАЦІЯ</b>",
        f"Instagram: {ig_line}",
        f"Регулярність: {reg_line}",
        f"Висновок по SMM: {_smm_conclusion(res)}",
        SEP, "",
        "<b>Під які послуги підходить:</b>",
        svc, "",
        "<i>Автооцінка — SEO Qualifier</i>",
    ]
    return "<br>".join(p)


def process_deal_debug(deal_id: str) -> dict:
    """Синхронний прогін із поверненням точної помилки на кроці, де вона сталась."""
    out = {"deal_id": deal_id}
    if not config.HUBSPOT_TOKEN:
        return {**out, "error": "no HUBSPOT_TOKEN"}
    try:
        props = get_deal(deal_id)
        out["pipeline"] = props.get("pipeline")
        out["domain"] = props.get(config.HUBSPOT_DEAL_DOMAIN_PROP)
    except Exception as e:
        return {**out, "step": "get_deal", "error": repr(e)[:400]}
    domain = (props.get(config.HUBSPOT_DEAL_DOMAIN_PROP) or "").strip()
    if not domain:
        return {**out, "step": "domain", "error": "empty domain"}
    try:
        res = qualify.qualify(domain, do_onpage=True,
                              do_ads=config.HUBSPOT_ENRICH, do_social=config.HUBSPOT_ENRICH)
        out["verdict"] = res.get("verdict")
    except Exception as e:
        return {**out, "step": "qualify", "error": repr(e)[:400]}
    try:
        dups = find_duplicate_deals(domain, deal_id)
        out["note_id"] = create_note(deal_id, _note_html(domain, res, dups))
        out["ok"] = True
    except Exception as e:
        return {**out, "step": "create_note", "error": repr(e)[:600]}
    return out


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
        dups = find_duplicate_deals(domain, deal_id)
        create_note(deal_id, _note_html(domain, res, dups))
        update_verdict_prop(deal_id, res.get("verdict", ""))
        log.info("deal %s (%s) -> %s, note created", deal_id, domain, res.get("verdict"))
    except Exception:
        log.exception("create_note failed for %s", deal_id)
