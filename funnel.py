# -*- coding: utf-8 -*-
"""Продуктова воронка: кому який оффер Elit-Web можна пропонувати і на яких умовах.

Адаптовано під наш (UA) аналізатор. Наша таблиця ніш містить лише SEO-придатність
(niche.OFFER_NO -> offer_fit). Придатність решти каналів (PPC, платні соцмережі, GEO,
ChatGPT Ads, CRO, Retention) виводимо евристично з НАПРЯМКУ ніші (ECOM/SERV/B2B/…) —
_derive_fits(). Це приблизна оцінка, тому в UI позначено «за напрямком ніші».

Ціни/умови — каталог офферів Elit-Web (USD), як у вихідному сервісі.

evaluate(raw) — ядро: приймає введені/підтягнуті дані, повертає оффери зі статусом
  offer  — пропонувати;  check — пропонувати після уточнення;  no — не підходить,
із причинами («why»), умовами й тим, що треба уточнити в клієнта («confirm»).
inputs_from_result(res, ...) — перетворює результат аналізатора на вхідні дані.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import config
import niche

CHANNELS = [("seo", "SEO"), ("ai", "AI-пошук (GEO)"), ("ppc", "Платний пошук (PPC)"),
            ("social", "Платні соцмережі"), ("cro", "CRO"), ("retention", "Retention"), ("smm", "SMM")]
STATUS_LABEL = {"offer": "Пропонувати", "check": "Уточнити", "no": "Не підходить"}

# Мінімальні рекламні бюджети з каталогу (USD/міс)
MIN_BUDGET = {"ppc_profit": 1500, "ppc_leads": 1000, "chatgpt": 1500, "social": 1000}

# Галузі з обмеженнями для ChatGPT Ads (потрібен додатковий ревʼю реклами)
_GPT_LIMITED_IND = {"MED"}
_GPT_LIMITED_CODES = {"PROF-01", "PROF-02", "PROF-03", "CONSTR-02"}
# Галузі з високим retention-потенціалом (повторні покупки / база клієнтів)
_RETENTION_IND = {"BEAUTY", "MED", "FOOD", "PERS"}


def _int(v) -> Optional[int]:
    try:
        if v in (None, ""):
            return None
        return int(float(str(v).replace(" ", "").replace(",", "")))
    except (TypeError, ValueError):
        return None


def _tri(v) -> str:
    v = str(v or "").strip().lower()
    return v if v in ("yes", "no") else "unknown"


def _derive_fits(ni: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Придатність каналів з напрямку ніші (евристика). None — коли ніша не обрана."""
    keys = ("ppc_fit", "social_fit", "geo_fit", "chatgpt_fit", "cro_fit", "retention_fit")
    if not ni:
        return {k: None for k in keys}
    d = ni.get("direction")
    ind = ni.get("industry") or ""
    code = ni.get("subniche_code") or ""
    is_spec = ind == "SPEC"
    ecom = d in ("ECOM", "RETAIL", "MARKET")

    if is_spec:
        ppc = "no"
    elif ecom:
        ppc = "profit"
    else:
        ppc = "leads"

    if is_spec:
        soc = "no"
    elif ecom:
        soc = "ecomm"
    elif d in ("SERV", "LOCAL", "SAAS"):
        soc = "leads"
    else:                      # B2B, MEDIA
        soc = "no"

    geo = "no" if is_spec else "yes"

    if is_spec:
        gpt = "no"
    elif ind in _GPT_LIMITED_IND or code in _GPT_LIMITED_CODES:
        gpt = "limited"
    else:
        gpt = "yes"

    cro = "no" if is_spec else "yes"

    if is_spec:
        ret = "no"
    elif ecom or ind in _RETENTION_IND:
        ret = "yes"
    else:
        ret = "limited"

    return {"ppc_fit": ppc, "social_fit": soc, "geo_fit": geo,
            "chatgpt_fit": gpt, "cro_fit": cro, "retention_fit": ret}


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Вхідні дані (форма або аналізатор) -> чистий словник."""
    code = (raw.get("niche") or "").strip() or None
    return {
        "niche": code,
        "site": "none" if str(raw.get("site") or "").strip() == "none" else "live",
        "visits": _int(raw.get("visits")),            # відвідувачі/міс з усіх джерел
        "organic": _int(raw.get("organic")),          # органічний пошук, візитів/міс
        "commercial": _int(raw.get("commercial")),    # комерц. запитів у TOP 4–20
        "google_ads": _tri(raw.get("google_ads")),
        "meta_ads": _tri(raw.get("meta_ads")),
        "tracking": _tri(raw.get("tracking")),        # GA4 + відстеження конверсій
        "budget": _int(raw.get("budget")),            # рекламний бюджет клієнта, $/міс
    }


def _money(n) -> str:
    return f"${int(n):,}"


def _offer(oid, channel, name, price, status, why, *, kpi=None, budget=None, terms=None,
           confirm=None, src="", variants=None) -> Dict[str, Any]:
    return {"id": oid, "channel": channel, "name": name, "price": price, "status": status,
            "status_label": STATUS_LABEL[status], "why": why, "kpi": kpi, "budget": budget,
            "terms": terms or [], "confirm": confirm or [], "src": src, "variants": variants or []}


def _budget_check(inp: Dict[str, Any], key: str, status: str, why: List[str]) -> str:
    """Якщо клієнт назвав бюджет нижче мінімуму — оффер лишається, але «check»."""
    b = inp["budget"]
    need = MIN_BUDGET[key]
    if b is not None and b < need and status == "offer":
        why.append(f"Названий рекламний бюджет {_money(b)}/міс нижчий за мінімум {_money(need)}/міс для цього офера.")
        return "check"
    return status


def evaluate(raw: Dict[str, Any]) -> Dict[str, Any]:
    inp = normalize(raw)
    ni = niche.result_for(inp["niche"]) if inp["niche"] else None
    fits = _derive_fits(ni)
    notes: List[str] = []
    if not inp["niche"]:
        notes.append("Оберіть нішу — більшість офферів залежать від неї.")
    elif ni is None:
        notes.append(f"Невідомий код ніші {inp['niche']!r}.")
    elif ni:
        notes.append("Придатність каналів (окрім SEO) визначено за напрямком ніші — приблизно; звіряйте з клієнтом.")

    seo_fit = ni["offer_fit"] if ni else None
    ppc_fit = fits["ppc_fit"]
    soc_fit = fits["social_fit"]
    gpt_fit = fits["chatgpt_fit"]
    cro_fit = fits["cro_fit"]
    geo_fit = fits["geo_fit"]
    ret_fit = fits["retention_fit"]
    no_table = False      # у нашій моделі придатність завжди виводиться

    live = inp["site"] == "live"
    traffic = inp["visits"] if inp["visits"] is not None else inp["organic"]
    organic = inp["organic"] if inp["organic"] is not None else inp["visits"]
    comm = inp["commercial"]
    kw_ok = comm is not None and comm >= config.COMMERCIAL_KW_MIN
    org_ok = organic is not None and organic >= config.TRAFFIC_MIN
    low_traffic = traffic is not None and traffic <= config.FUNNEL_LOW_TRAFFIC
    few_kw = comm is not None and comm < config.COMMERCIAL_KW_MIN
    out: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ SEO
    if not live:
        out.append(_offer("seo_dev", "seo", "SEO на етапі розробки", "Пакети $180 / $360 / $540", "offer",
                          ["Сайту ще немає / у розробці — цей пакет створений саме для такого випадку."],
                          src="SEO #1"))
    else:
        out.append(_offer("seo_dev", "seo", "SEO на етапі розробки", "Пакети $180 / $360 / $540", "no",
                          ["Сайт уже працює — цей пакет лише для сайтів, яких ще немає або вони в розробці."],
                          src="SEO #1"))

    # Ongoing SEO (фікс)
    ongoing_price = "$1,600 на місяць"
    ongoing_terms = ["50% ціни покриває витрати, 50% — роботу команди"]
    why = []
    if not live:
        st = "no"; why.append("Сайту ще немає — почніть із пакета на етапі розробки.")
    elif seo_fit is False:
        st = "offer"; why.append("Ніша не підходить під KPI-модель, тож SEO продається фіксованими місячними пакетами.")
    elif low_traffic and few_kw:
        st = "offer"
        why.append(f"Нуль / дуже низький трафік (≤{config.FUNNEL_LOW_TRAFFIC:,} візитів/міс) і менше ніж "
                   f"{config.COMMERCIAL_KW_MIN} комерційних запитів — профіль, під який створено цей пакет.")
    elif traffic is None or comm is None:
        st = "check"; why.append("Додайте трафік і кількість комерційних запитів, щоб зрозуміти, чи проєкт у діапазоні низького трафіку "
                                 f"(≤{config.FUNNEL_LOW_TRAFFIC:,} візитів/міс і <{config.COMMERCIAL_KW_MIN} комерційних запитів).")
    else:
        st = "no"; why.append("Трафік і комерційні запити вищі за діапазон низького трафіку — основний оффер це SEO за результат.")
    out.append(_offer("seo_ongoing", "seo", "Постійне SEO (фікс/міс)", ongoing_price, st, why,
                      terms=ongoing_terms, src="SEO #2"))

    # Performance-driven SEO (SEO за результат / KPI)
    perf_terms = ["KPI: трафік, ліди, конверсія",
                  "Робоча частина $1,800 залежить від виконання KPI: нижче плану → менше, вище → більше",
                  "Низький трафік: спершу фікс $1,600/міс на 3–4 місяці, потім перехід на цю модель"]
    perf_price = "$600 витрати (контент + посилання) + $1,800 за роботу за виконання KPI"
    why = []
    if seo_fit is None and not no_table:
        st = "check"; why.append("Оберіть нішу, щоб побачити, чи підходить вона під KPI-модель.")
    elif seo_fit is False:
        st = "no"; why.append("Ніша позначена «Ні» для офера «SEO за KPI» у таблиці ніш.")
    elif not live:
        st = "no"; why.append("Потрібен робочий сайт з певною історією — спершу пакет на етапі розробки.")
    elif traffic is None and comm is None:
        st = "check"; why.append("Ніша підходить під KPI-модель. Додайте органічний трафік і кількість комерційних запитів для підтвердження.")
    elif kw_ok and org_ok:
        st = "offer"
        why.append("Ніша підходить під KPI-модель (таблиця: SEO за KPI = Так).")
        why.append(f"Кваліфікується: ~{_int(organic):,} орг. візитів/міс (≥{config.TRAFFIC_MIN:,}) і ~{comm:,} комерційних запитів (≥{config.COMMERCIAL_KW_MIN}).")
    else:
        st = "check"
        why.append("Ніша підходить під KPI-модель, але проєкт нижчий за пороги "
                   f"(≥{config.TRAFFIC_MIN:,} орг. візитів/міс і ≥{config.COMMERCIAL_KW_MIN} комерційних запитів).")
        if out[1]["status"] == "offer":
            why.append("План: фікс Постійне SEO ($1,600/міс) на 3–4 місяці, потім перехід на модель за результат.")
        else:
            why.append("Перевірте потенціал зростання перед пропозицією KPI-моделі.")
    out.append(_offer("seo_perf", "seo", "SEO за результат (KPI)", perf_price, st, why, kpi="Трафік, ліди, конверсія",
                      terms=perf_terms, src="SEO #3"))

    # GEO / AI Search
    geo_terms = ["Включає 150 промптів у нашому дашборді Eligo"]
    geo_confirm = ["Клієнти використовують ChatGPT / Gemini / Perplexity для пошуку чи порівняння в цій ніші",
                   "Здоровий SEO-фундамент: індексація, органічний трафік, позиції в Google, якісний контент",
                   "Видимість може перетворитися на ліди / продажі / нових клієнтів",
                   "Клієнт готовий інвестувати в GEO"]
    why = []
    if geo_fit is None:
        st = "check"; why.append("Оберіть нішу, щоб побачити придатність GEO.")
    elif geo_fit == "no":
        st = "no"; why.append("Ніша не позначена як придатна для GEO.")
    elif not live:
        st = "no"; why.append("Сайту ще немає — GEO потребує індексованого сайту з SEO-фундаментом.")
    elif organic is None:
        st = "check"; why.append("Ніша підходить під GEO. Додайте органічний трафік для перевірки SEO-фундаменту.")
    elif organic >= config.FUNNEL_GEO_MIN_ORGANIC:
        st = "offer"; why.append("Ніша підходить під GEO.")
        why.append(f"SEO-фундамент виглядає ок: ~{organic:,} орг. візитів/міс.")
    elif organic >= 100:
        st = "check"; why.append(f"Ніша підходить під GEO, але SEO-фундамент слабкий (~{organic:,} орг. візитів/міс) — "
                                 f"найкраще від ≥{config.FUNNEL_GEO_MIN_ORGANIC:,}.")
    else:
        st = "no"; why.append("Ніша підходить під GEO, але органіки майже немає — спершу збудуйте SEO, потім додавайте GEO.")
    out.append(_offer("geo", "ai", "GEO / Оптимізація під AI-пошук", "$1,200 робота + від $1,500 витрати", st, why,
                      terms=geo_terms, confirm=geo_confirm, src="SEO #4"))

    # ------------------------------------------------------------------ PPC
    ppc_terms = ["Власний кабінет клієнта"]
    def _ppc(oid, name, price, kind, kpi, budget_key, budget_txt, active_note=None):
        why = []
        if ppc_fit is None:
            st = "check"; why.append("Оберіть нішу, щоб побачити PPC-модель.")
        elif ppc_fit != kind:
            labels = {"profit": "для Profit (ecom)", "leads": "для Leads", "no": "«Ні» (не під KPI-модель)"}
            st = "no"; why.append(f"Ніша позначена {labels[ppc_fit]} для PPC — застосовується інша PPC-модель.")
        else:
            st = "offer"
            why.append({"profit": "Ніша підходить під Profit-Driven PPC (напрямок: ecommerce).",
                        "leads": "Ніша підходить під Pay-Per-Lead PPC (лідогенерація)."}[kind])
            if active_note:
                why.append(active_note)
            st = _budget_check(inp, budget_key, st, why)
        return _offer(oid, "ppc", name, price, st, why, kpi=kpi, budget=budget_txt, terms=ppc_terms,
                      confirm=(["Чи запускають рекламу зараз? (ціна залежить від цього)"] if kind == "profit" and inp["google_ads"] == "unknown" else []),
                      src={"ppc_profit": "PPC #1–2", "ppc_leads": "PPC #3"}[oid])

    if inp["google_ads"] == "yes":
        price_profit = "$300 фікс + бонус за ріст виручки (реклама вже працює)"
        note = "Реклама вже працює → застосовується варіант $300 фікс."
    elif inp["google_ads"] == "no":
        price_profit = "$400 фікс + бонус за ріст виручки (раніше не рекламувались)"
        note = "Реклами немає → застосовується варіант $400 фікс."
    else:
        price_profit = "$400 фікс + бонус (раніше не рекламувались) · $300 фікс + бонус (реклама вже працює)"
        note = None
    out.append(_ppc("ppc_profit", "Profit-Driven PPC (ecom)", price_profit, "profit",
                    "ROAS / ACOS + ріст виручки", "ppc_profit", "Рекламний бюджет від $1,500/міс", note))
    out.append(_ppc("ppc_leads", "Pay-Per-Lead PPC (лідогенерація)", "$300 фікс + оплата за лід з реклами", "leads",
                    "Кількість лідів", "ppc_leads", "Рекламний бюджет від $1,000/міс"))
    out.append(_offer("ppc_mgmt", "ppc", "Ведення PPC (без KPI-моделі)", "$800/міс за ведення",
                      "offer" if (ppc_fit == "no") else "no",
                      ["Ніша не під PPC-за-KPI — продаємо звичайне ведення."] if ppc_fit == "no"
                      else ["Лише для ніш, що не підходять під KPI-модель."], src="PPC #6"))

    # ChatGPT Ads
    gpt_terms = ["Потрібно: сайт, відстеження конверсій і тестовий бюджет; рекламна платформа має бути доступна на ринку клієнта"]
    why = []
    if gpt_fit is None:
        st = "check"; why.append("Оберіть нішу, щоб побачити правило для ChatGPT Ads.")
    elif gpt_fit == "no":
        st = "no"; why.append("Не пропонується для цієї ніші (gambling, betting, adult, crypto — лише після ревʼю продуктового відділу).")
    elif gpt_fit == "limited":
        st = "check"; why.append("Лише після погодження: ця категорія потребує додаткового ревʼю реклами (типово для медицини, фінансів, юридики, нерухомості).")
    else:
        st = "offer"; why.append("Ніша — дозволена категорія для ChatGPT Ads.")
    if st in ("offer", "check") and inp["tracking"] == "no":
        st = "check"; why.append("Немає відстеження конверсій — це вимога для цього офера.")
    if st == "offer":
        st = _budget_check(inp, "chatgpt", st, why)
    out.append(_offer("chatgpt", "ppc", "ChatGPT Ads", "$800 перший місяць, $700 з 2-го місяця", st, why,
                      budget="Рекламний бюджет від $1,500/міс", terms=gpt_terms,
                      confirm=["Рекламна платформа доступна на ринку клієнта", "Налаштоване відстеження конверсій", "Є бюджет на тест"],
                      src="PPC #4"))
    bundle_ok = (ppc_fit in ("profit", "leads", "no")) and gpt_fit in ("yes", "limited")
    out.append(_offer("ppc_chatgpt", "ppc", "Бандл PPC + ChatGPT Ads", "−$300 на ChatGPT Ads при купівлі разом з PPC",
                      ("offer" if gpt_fit == "yes" else "check") if bundle_ok else "no",
                      ["Підходить і під PPC, і під ChatGPT Ads → пропонуйте разом зі знижкою."
                       + (" ChatGPT Ads все ще потребує погодження для цієї ніші." if gpt_fit == "limited" else "")] if bundle_ok
                      else ["Потрібні і PPC-модель, і придатність для ChatGPT Ads."], src="PPC #5"))

    # ---------------------------------------------------------- Paid social
    soc_price = "$800 перший місяць, далі $450/міс + KPI-бонус"
    soc_terms_common = ["Кабінет клієнта показує виконання KPI і вузькі місця",
                        "Ціна розрахована на проєкти, що раніше не запускали платні соцмережі"]
    def _soc(oid, name, kind, kpi, extra_terms, variants=None):
        why = []
        if soc_fit is None:
            st = "check"; why.append("Оберіть нішу, щоб побачити модель платних соцмереж.")
        elif soc_fit != kind:
            labels = {"ecomm": "для Ecomm", "leads": "для Leads", "no": "«Ні» (не під KPI-модель)"}
            st = "no"; why.append(f"Ніша позначена {labels[soc_fit]} для платних соцмереж — застосовується інша модель.")
        else:
            st = "offer"
            why.append({"ecomm": "Ніша підходить під performance-соцмережі для ecom.",
                        "leads": "Ніша підходить під performance-соцмережі для лідогенерації."}[kind])
            if inp["meta_ads"] == "yes":
                why.append("Вже запускають Meta Ads — каталог розрахований на нових рекламодавців; уточніть умови для активного.")
            st = _budget_check(inp, "social", st, why)
        return _offer(oid, "social", name, soc_price, st, why, kpi=kpi, budget="Рекламний бюджет $1,000–1,500/міс",
                      terms=soc_terms_common + extra_terms, variants=variants or [],
                      src={"social_ecomm": "Paid Social #1", "social_leads": "Paid Social #2"}[oid])
    out.append(_soc("social_ecomm", "Performance-соцмережі — Ecomm", "ecomm",
                    "Виручка, замовлення, середній чек, ROAS", [],
                    variants=["Допродаж: Meta + TikTok за KPI — $600 фікс", "Допродаж: Meta + TikTok + відеопродакшн — $750 фікс"]))
    out.append(_soc("social_leads", "Performance-соцмережі — LeadGen", "leads",
                    "Ліди, вартість ліда, % кваліфікованих лідів, ROAS", []))
    out.append(_offer("social_mgmt", "social", "Ведення платних соцмереж (без KPI)", "$800/міс за ведення",
                      "offer" if soc_fit == "no" else "no",
                      ["Ніша не під соцмережі-за-KPI — продаємо звичайне ведення."] if soc_fit == "no"
                      else ["Лише для ніш, що не підходять під KPI-модель."], src="Paid Social #3"))

    # ------------------------------------------------------------------ CRO
    cro_confirm = ["Сайт уже генерує ліди, покупки чи реєстрації",
                   "Налаштований GA4 і відстежуються ключові конверсії",
                   "Є простір підняти конверсію без пропорційного росту реклами"]
    why = []
    if cro_fit is None:
        st = "check"; why.append("Оберіть нішу, щоб побачити придатність CRO.")
    elif cro_fit == "no":
        st = "no"; why.append("Ніша не позначена як придатна для CRO.")
    elif not live:
        st = "no"; why.append("Ще немає робочого сайту для оптимізації.")
    elif inp["visits"] is None and inp["organic"] is None:
        st = "check"; why.append(f"Ніша підходить під CRO. Додайте місячний трафік — потрібно ~{config.FUNNEL_CRO_TRAFFIC:,} відвідувачів для A/B-тестів.")
    else:
        cro_traffic = inp["visits"] if inp["visits"] is not None else inp["organic"]
        if cro_traffic >= config.FUNNEL_CRO_TRAFFIC:
            st = "offer"; why.append(f"Ніша підходить під CRO і трафіку достатньо для тестів (~{cro_traffic:,} відвідувачів/міс, бажано ≥{config.FUNNEL_CRO_TRAFFIC:,}).")
        else:
            st = "check"
            lab = "відвідувачів/міс" if inp["visits"] is not None else "орг. візитів/міс (загальний трафік може бути вищим)"
            why.append(f"Ніша підходить під CRO, але ~{cro_traffic:,} {lab} нижче бажаних {config.FUNNEL_CRO_TRAFFIC:,} — "
                       "орієнтуйтесь на кількість конверсій.")
        if inp["tracking"] == "no":
            st = "check"; why.append("GA4 / відстеження конверсій не налаштовано — спершу це.")
    out.append(_offer("cro", "cro", "CRO-аудит", "$3,600 · 15 робочих днів (постійне CRO — окремо)", st, why,
                      confirm=cro_confirm, src="CRO"))

    # ------------------------------------------------------------ Retention
    why = []
    if ret_fit is None:
        st = "check"; why.append("Оберіть нішу, щоб побачити придатність Retention.")
    elif ret_fit == "no":
        st = "no"; why.append("Ніша не позначена як придатна для Retention.")
    elif ret_fit == "limited":
        st = "check"; why.append("Retention підходить лише в обмежених випадках — спершу перевірте базу клієнтів.")
    else:
        st = "offer"; why.append("Ніша підходить під Retention-маркетинг.")
    out.append(_offer("retention", "retention", "Retention-маркетинг", "$1,400 + витрати на сервіси", st, why,
                      confirm=["Є база клієнтів / потенціал повторних покупок"], src="Retention"))

    # ------------------------------------------------------------------ SMM
    out.append(_offer("smm", "smm", "SMM (ведення соцмереж)", "Пакети $600 / $800 / $1,600", "check",
                      ["Немає правила по ніші — опційний допродаж; пропонуйте, коли клієнт хоче органічну присутність у соцмережах."],
                      src="SMM"))

    # ------------------------------------------------------- lead-with stack
    prio = ["seo_dev", "seo_perf", "seo_ongoing", "ppc_profit", "ppc_leads", "social_ecomm", "social_leads",
            "ppc_mgmt", "social_mgmt", "geo", "chatgpt", "cro", "retention"]
    if not live:
        # сайту ще нема — пропонуємо лише SEO на етапі розробки, решта послуг не додається
        out = [o for o in out if o["id"] == "seo_dev"]
        notes.append("Сайту ще немає — застосовне лише SEO на етапі розробки; решту послуг не додано.")
    byid = {o["id"]: o for o in out}
    prio = [i for i in prio if i in byid]
    lead = [i for i in prio if byid[i]["status"] == "offer"][:3]
    if len(lead) < 2:
        lead += [i for i in prio if byid[i]["status"] == "check" and i not in lead][: 2 - len(lead)]
    return {
        "niche": ({"code": ni["subniche_code"], "name": ni["subniche"], "industry": ni["industry_name"],
                   "seo_fit": seo_fit, "ppc_fit": ppc_fit, "social_fit": soc_fit} if ni else None),
        "inputs": inp, "offers": out, "lead_with": lead, "notes": notes,
        "summary": summary_text(inp, ni, out, lead),
    }


def summary_text(inp, ni, offers: List[Dict[str, Any]], lead: List[str]) -> str:
    """Короткий текст для копіювання (CRM/чат): що пропонувати й за скільки."""
    lines = []
    if ni:
        lines.append(f"Ніша: {ni['industry_name']} → {ni['subniche']}")
    byid = {o["id"]: o for o in offers}
    if lead:
        lines.append("Пропонувати в першу чергу:")
        for i in lead:
            o = byid[i]
            lines.append(f"• {o['name']} — {o['price']}" + (" (уточнити)" if o["status"] == "check" else ""))
    rest = [o for o in offers if o["status"] == "offer" and o["id"] not in lead]
    if rest:
        lines.append("Також підходить:")
        for o in rest:
            lines.append(f"• {o['name']} — {o['price']}")
    chk = [o for o in offers if o["status"] == "check" and o["id"] not in lead and o["id"] != "smm"]
    if chk:
        lines.append("Можливо після уточнень: " + ", ".join(o["name"] for o in chk))
    return "\n".join(lines)


def niche_choices() -> List[Tuple[str, List[Tuple[str, str]]]]:
    """[(industry_name, [(code, label), ...]), ...] для випадного списку ніш."""
    groups: Dict[str, List[Tuple[str, str]]] = {}
    order: List[str] = []
    for code, ind, name, _dir, _kw in niche.SUB:
        iname = niche.INDUSTRIES.get(ind, ind)
        if iname not in groups:
            groups[iname] = []
            order.append(iname)
        tag = "" if code not in niche.OFFER_NO else " · не під SEO-KPI"
        groups[iname].append((code, f"{name}{tag}"))
    return [(n, groups[n]) for n in order]


# ------------------------------------------------------------ з аналізатора

def inputs_from_result(res: Dict[str, Any], visits: Optional[int] = None,
                       ads: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Дані аналізатора -> (вхід для evaluate, джерела/нотатки по полях).
    ads — компактна реклама або None; visits — відвідувачі/міс (Traffic Analytics)."""
    src: Dict[str, str] = {}
    ni = res.get("niche") or {}
    mt = res.get("metrics") or {}
    paid = res.get("paid") or {}
    code = ni.get("subniche_code")
    if code:
        conf = ni.get("confidence")
        src["niche"] = ("визначено аналізатором" + (" — низька впевненість, перевірте" if conf == "низька" else ""))
    organic = mt.get("organic_traffic")
    reachable = mt.get("reachable")
    site = "live"
    if reachable is False and not organic:
        site = "none"
        src["site"] = "сайт був недоступний під час перевірки — підтвердіть, що він не просто лежить або ще в розробці"
    else:
        src["site"] = "сайт відповів під час перевірки"
    if organic is not None:
        src["organic"] = "SemRush, орг. візитів/міс для обраного ринку"
    if mt.get("commercial_kw_11_30") is not None:
        src["commercial"] = "аналізатор: комерційні запити в TOP 4–20 (модельовано)"
    if visits is not None:
        src["visits"] = "Traffic Analytics, унікальних відвідувачів/міс"

    g = m = "unknown"
    gads, mads = ((ads or {}).get("google") or {}), ((ads or {}).get("meta") or {})
    if (paid.get("traffic") or 0) > 0 or (res.get("ads") or {}).get("running") or gads.get("running"):
        g = "yes"; src["google_ads"] = "виявлено рекламу (SemRush paid traffic / Ads Transparency)"
    elif gads.get("checked") or (res.get("ads") or {}).get("checked"):
        g = "no"; src["google_ads"] = "Ads Transparency Center: реклами за останні дні немає"
    if (res.get("meta_ads") or {}).get("running") or mads.get("running"):
        m = "yes"; src["meta_ads"] = "Meta Ad Library: знайдено активну рекламу"
    elif (res.get("meta_ads") or {}).get("checked") or mads.get("checked"):
        m = "no"; src["meta_ads"] = "Meta Ad Library: активної реклами немає"
    raw = {"niche": code, "site": site, "visits": visits, "organic": organic,
           "commercial": mt.get("commercial_kw_11_30"), "google_ads": g, "meta_ads": m,
           "tracking": "unknown", "budget": None}
    return raw, src
