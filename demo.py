# -*- coding: utf-8 -*-
"""Демо-результат для перевірки інтерфейсу без витрати API-квоти (SemRush/SerpApi).
Повертає повний res-словник, як його будує qualify.qualify, з усіма блоками:
трафік+прогноз, матриця позицій, потенціал/економіка, медіаплан, контекст
(формати+платформи+креативи), Shopping, соцмережі, ТОП сторінки, послуги, кейси."""
from __future__ import annotations
import base64
import datetime
import charts
import qualify


def _trend_points():
    vals = [54, 57, 55, 60, 63, 61, 66, 70, 68, 74, 79, 82]
    today = datetime.date.today()
    pts = []
    for i, v in enumerate(vals):
        m = today.month - (len(vals) - 1 - i)
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        ts = int(datetime.datetime(y, m, 1).timestamp())
        pts.append({"value": v, "ts": ts, "label": f"{m:02d}.{y}"})
    return pts

def _kwplan():
    vols = [12100, 13200, 12800, 14500, 15800, 15100, 17200, 18900, 18100, 20400, 22600, 24100]
    today = datetime.date.today()
    labels = []
    for i in range(len(vols)):
        m = today.month - (len(vols) - 1 - i)
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        labels.append(f"{m:02d}.{str(y)[2:]}")
    return {
        "keywords": [
            {"keyword": "лазерна епіляція київ", "volume": 8100, "cpc": 9.45, "competition": "HIGH"},
            {"keyword": "косметологія київ", "volume": 5400, "cpc": 7.80, "competition": "HIGH"},
            {"keyword": "чистка обличчя", "volume": 4400, "cpc": 5.20, "competition": "MEDIUM"},
            {"keyword": "ботокс ціна", "volume": 3600, "cpc": 11.30, "competition": "HIGH"},
            {"keyword": "мезотерапія обличчя", "volume": 2900, "cpc": 8.10, "competition": "MEDIUM"},
        ],
        "total_ideas": 742,
        "trend": vols,
        "trend_labels": labels,
        "change_pct": 99,
        "source": "Google Keyword Planner",
    }


def _cro_demo():
    return {
        "checked": True, "score_total": 42, "score_label": "Критично",
        "domain": "demo-klinika.ua",
        "categories": {
            "speed": {"score": 38, "label": "потребує уваги"},
            "ux": {"score": 52, "label": "середньо"},
            "cta": {"score": 40, "label": "слабко"},
            "trust": {"score": 63, "label": "добре"},
        },
        "summary": ("Сайт має базову структуру медичного центру з наявним соціальним доказом, телефоном і "
                    "чатом, однак критично втрачає конверсії через три ключові проблеми: примусовий мовний "
                    "попап, що блокує контент при вході, слабкий H1 без ціннісної пропозиції та неправильну "
                    "ієрархію CTA (акції важливіші за запис). Найбільший потенціал росту — переробка hero-"
                    "секції (H1 + CTA + мікроформа) і усунення мовного попапу, що разом може підняти "
                    "конверсію сторінки на 30–50%."),
        "quick_wins": [
            "Модальне вікно мови блокує весь контент при вході",
            "Первинний CTA 'НАШІ АКЦІЇ' не веде до конверсії",
            "H1 не передає жодної вигоди клієнту",
        ],
        "issues": [
            {"category": "ux", "priority": "critical", "priority_label": "Критично",
             "title": "Модальне вікно мови блокує контент",
             "problem": "Попап вибору мови перекриває весь екран при вході й змушує зробити зайву дію.",
             "impact": "Втрата до 20% відвідувачів на першому екрані.",
             "recommendation": "Прибрати примусовий попап; визначати мову автоматично з можливістю зміни в шапці.",
             "benchmark": "Топ-сайти не блокують контент модалками при вході.",
             "screenshot": "https://placehold.co/520x260/1a1a20/00C2B2?text=header"},
            {"category": "cta", "priority": "critical", "priority_label": "Критично",
             "title": "Первинний CTA 'НАШІ АКЦІЇ' не веде до конверсії",
             "problem": "Головна кнопка веде на акції, а не на запис — цільова дія втрачається.",
             "impact": "Розмиває основний потік конверсії (запис на прийом).",
             "recommendation": "Зробити головним CTA «Записатися», акції — другорядним посиланням.",
             "benchmark": "Один чіткий первинний CTA на першому екрані."},
            {"category": "ux", "priority": "critical", "priority_label": "Критично",
             "title": "H1 не передає вигоди клієнту",
             "problem": "Заголовок не містить ціннісної пропозиції та ключового запиту."},
            {"category": "speed", "priority": "important", "priority_label": "Важливо",
             "title": "Повільний LCP (4.1 c)",
             "problem": "Велике héro-зображення блокує відображення першого екрана."},
            {"category": "trust", "priority": "important", "priority_label": "Важливо",
             "title": "Відгуки не біля форми запису",
             "problem": "Соціальний доказ рознесений по сторінці, не підкріплює цільову дію."},
            {"category": "ux", "priority": "important", "priority_label": "Важливо",
             "title": "Форма запису задовга",
             "problem": "6 полів знижують відсоток завершення форми."},
            {"category": "cta", "priority": "improvement", "priority_label": "Покращення",
             "title": "Немає липкої кнопки дзвінка на мобільному",
             "problem": "На мобільному контакт не завжди в зоні видимості."},
            {"category": "trust", "priority": "improvement", "priority_label": "Покращення",
             "title": "Немає сертифікатів/ліцензій у футері",
             "problem": "Для меддомену це знижує сприйняту надійність."},
        ],
        "issues_total": 8,
        "pagespeed": {"score": 59, "lcp": "4.1 c", "fcp": "2.3 c", "cls": "0.08", "tbt": "310 ms", "si": "5.2 c"},
        "link": "https://cro-auditor-production.up.railway.app",
    }


DEMO_DOMAIN = "demo-klinika.ua"


def _banner(w, h, label, bg):
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'>"
           f"<rect width='100%' height='100%' fill='{bg}'/>"
           f"<rect x='6' y='6' width='{w-12}' height='{h-12}' fill='none' stroke='#fff' "
           f"stroke-opacity='0.5' stroke-width='2' rx='8'/>"
           f"<text x='50%' y='42%' fill='#fff' font-family='Arial' font-size='16' "
           f"font-weight='bold' text-anchor='middle'>{label}</text>"
           f"<text x='50%' y='64%' fill='#fff' font-family='Arial' font-size='12' "
           f"text-anchor='middle' opacity='0.9'>demo-klinika.ua</text></svg>")
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _history():
    dates = ["202507", "202508", "202509", "202510", "202511", "202512",
             "202601", "202602", "202603", "202604", "202605", "202606"]
    vals = [16800, 17500, 17100, 15900, 15200, 17400,
            16100, 16900, 18200, 19100, 20100, 20700]
    # свіжі першими (як віддає SemRush history)
    return [{"date": d, "org_traffic": v}
            for d, v in zip(reversed(dates), reversed(vals))]


def demo_result() -> dict:
    hist = _history()

    conv, check, margin, close = 3.5, 4000, 60, 40
    w_uplift, w_t1 = 23000, 30000
    apps = round(w_uplift * conv / 100)          # 805
    sales = round(apps * close / 100)            # 322
    revenue = round(sales * check)               # 1 288 000
    profit = round(revenue * margin / 100)       # 772 800
    benefit = {
        "queries": 743, "queries_sampled": 180, "modeled": True,
        "traffic_now": 24304, "traffic_top1": 106283,
        "uplift": 106283 - 24304, "multiplier": round(106283 / 24304, 1),
        "conv_pct": conv, "avg_check": check, "avg_margin": margin, "close_pct": close,
        "conv_type": "Лід/заявка", "conv_quality_pct": 71,
        "w_uplift": w_uplift, "w_t1": w_t1,
        "apps_uplift": apps, "apps_top1": round(w_t1 * conv / 100),
        "sales_uplift": sales, "sales_top1": round(w_t1 * conv / 100 * close / 100),
        "revenue_uplift": revenue, "revenue_top1": round(w_t1 * conv / 100 * close / 100 * check),
        "profit_uplift": profit, "profit_top1": round(w_t1 * conv / 100 * close / 100 * check * margin / 100),
    }

    media_plan = qualify.build_media_plan(150000, 9.45, conv, check, margin, close)

    segments = {
        "labels": {"top3": "ТОП 3", "p4_10": "4–10", "p11_20": "11–20",
                   "p21_50": "21–50", "p51_100": "51–100"},
        "segments": {"top3": 235, "p4_10": 609, "p11_20": 333, "p21_50": 657, "p51_100": 343},
        "total": 2177, "capped": False,
    }

    top_pages_traffic = [
        {"url": "demo-klinika.ua/apparatna-kosmetologiya/", "traffic": 3120, "keywords": 210, "q_4_20": 48, "traffic_pot": 7800},
        {"url": "demo-klinika.ua/laser-epilation/", "traffic": 2540, "keywords": 178, "q_4_20": 41, "traffic_pot": 6100},
        {"url": "demo-klinika.ua/botox/", "traffic": 1980, "keywords": 143, "q_4_20": 33, "traffic_pot": 4700},
        {"url": "demo-klinika.ua/lpg-massage/", "traffic": 1520, "keywords": 96, "q_4_20": 22, "traffic_pot": 3400},
        {"url": "demo-klinika.ua/pricing/", "traffic": 1180, "keywords": 74, "q_4_20": 18, "traffic_pot": 2600},
    ]
    dotisk = [
        {"keyword": "лазерна епіляція київ", "position": 6, "volume": 8100, "cpc": 0.9,
         "url": "demo-klinika.ua/laser-epilation/", "traffic_now": 486, "traffic_top1": 2560},
        {"keyword": "апаратна косметологія", "position": 5, "volume": 5400, "cpc": 0.7,
         "url": "demo-klinika.ua/apparatna-kosmetologiya/", "traffic_now": 378, "traffic_top1": 1706},
        {"keyword": "ботокс ціна", "position": 8, "volume": 2900, "cpc": 0.6,
         "url": "demo-klinika.ua/botox/", "traffic_now": 145, "traffic_top1": 916},
    ]

    ads = {
        "checked": True, "running": True, "count": 24, "advertisers": ["demo-klinika.ua"],
        "period_days": 7,
        "formats": {"text": 15, "image": 8, "video": 1, "other": 0},
        "formats_sampled": 24,
        "platforms": {"search": 15, "youtube": 4, "shopping": 3, "maps": 2, "play": 0},
        "platform_labels": {"search": "Пошук Google", "youtube": "YouTube",
                            "shopping": "Google Покупки", "maps": "Карти Google", "play": "Google Play"},
        "creatives": [
            {"format": "image", "image": _banner(300, 250, "Косметологія −20%", "#C12814"), "text": "", "link": "", "platforms": ["search", "shopping"]},
            {"format": "image", "image": _banner(336, 280, "Лазерна епіляція", "#15151B"), "text": "", "link": "", "platforms": ["shopping"]},
            {"format": "text", "image": "", "text": "Естетична косметологія у Києві — консультація безкоштовно", "link": "", "platforms": ["search"]},
            {"format": "text", "image": "", "text": "Лазерна епіляція від 199 грн · запис онлайн", "link": "", "platforms": ["search"]},
            {"format": "video", "image": "", "text": "", "link": "https://adstransparency.google.com/?region=UA&domain=demo-klinika.ua", "platforms": ["youtube"]},
        ],
        "link": "https://adstransparency.google.com/?region=UA&domain=demo-klinika.ua",
    }

    shopping = {"checked": True, "uses": True, "pla_keywords": 6, "sampled": 10,
                "shop_name": "Demo Klinika", "products": []}
    meta_ads = {
        "checked": True, "running": True, "count": 14, "page": "Demo Klinika",
        "platforms": {"facebook": 14, "instagram": 12, "messenger": 5, "audience_network": 3},
        "creatives": [
            {"image": _banner(300, 300, "Акція −25%", "#1877F2"), "link": "", "platforms": ["facebook", "instagram"],
             "text": "Косметологія у Києві зі знижкою 25% на перший візит. Запишись онлайн за хвилину.", "cta": "Записатися", "format": "image", "start": "2026-06-11", "versions": 2},
            {"image": _banner(300, 300, "Запис онлайн", "#C12814"), "link": "", "platforms": ["instagram"],
             "text": "Лазерна епіляція без болю — консультація безкоштовно.", "cta": "Написати", "format": "video", "start": "2026-07-01", "versions": 1},
            {"image": _banner(300, 300, "Консультація", "#15151B"), "link": "", "platforms": ["facebook"],
             "text": "Естетична медицина: ботокс, мезотерапія, чистка обличчя. Перший огляд — 0 грн.", "cta": "Дізнатися ціну", "format": "image", "start": "2026-05-20", "versions": 3},
            {"image": _banner(300, 300, "Лазер від 199₴", "#159A4B"), "link": "", "platforms": ["instagram", "facebook"],
             "text": "Лазер від 199 грн за зону. Тільки цього місяця.", "cta": "Записатися", "format": "video", "start": "2026-07-10", "versions": 1},
        ],
        "link": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=UA&q=demo-klinika",
    }
    paid = {"keywords": 84, "traffic": 1200, "budget": 3400}
    social = {"checked": True, "found": True, "handle": "demo_klinika", "url": "#",
              "followers": 48200, "is_private": False, "active": True, "avg_engagement": 620}

    services = [
        {"name": "SEO за ТОП", "level": "yes", "note": "є комерційні позиції, трафік і потенціал під офер"},
        {"name": "Базове SEO", "level": "yes", "note": "є SEO-база для щомісячного просування"},
        {"name": "Контекстна реклама", "level": "yes", "note": "вже інвестує в контекст — можна вести/оптимізувати"},
        {"name": "SMM (соцмережі)", "level": "yes", "note": "є аудиторія (~48 200 підписників) — SMM доречний"},
        {"name": "Таргет (Meta)", "level": "yes", "note": "вже крутить таргет (~14 крео) — можна масштабувати"},
    ]
    factors = [
        {"name": "Ніша під офер", "value": "профільна", "ok": True},
        {"name": "Комерційні запити (4–20)", "value": 743, "ok": True, "target": 300,
         "kind": "ratio", "pct": 100},
        {"name": "SEO-трафік / міс", "value": 24304, "ok": True, "target": 10000,
         "kind": "ratio", "pct": 100},
        {"name": "Потенціал зростання", "value": 24304, "ok": True, "kind": "growth",
         "z1": 20, "z2": 55, "marker": 82, "tier": "сильний"},
        {"name": "SEO-оптимізація", "value": "добра", "ok": True},
        {"name": "Широка структура (орг. ключів)", "value": 2585, "ok": True},
    ]
    cases = [
        {"domain": "hold.ua", "country": "Україна", "country_flag": "🇺🇦",
         "service": "SEO за ТОП", "niche": "Меблі",
         "links": {"kp": "#", "ext": "#", "blog": ""}},
    ]

    return {
        "domain": DEMO_DOMAIN,
        "error": None,
        "verdict": "ІДЕАЛЬНО", "score": 92, "color": "green",
        "niche": {"direction": "SERV", "direction_name": "Послуги",
                  "industry": "MED", "industry_name": "Медицина і фарма (послуги)",
                  "subniche": "Естетична медицина", "subniche_code": "MED-03",
                  "confidence": "висока", "offer_fit": True,
                  "conv_pct": conv, "avg_check": check, "avg_margin": margin,
                  "close_pct": close, "conv_type": "Лід/заявка", "cpc": 9.45},
        "niche_caveat": False, "kw_caveat": False,
        "metrics": {"organic_traffic": 24304, "organic_keywords": 2585,
                    "commercial_kw_11_30": 743, "optimized": True, "opt_assessable": True},
        "segments": segments,
        "history": hist,
        "traffic_svg": charts.traffic_svg(hist, months=12, theme="dark"),
        "forecast_svg": charts.forecast_svg(hist, benefit["traffic_top1"], theme="dark"),
        "benefit": benefit,
        "media_plan": media_plan,
        "top_pages_traffic": top_pages_traffic,
        "top_pages_seo": [],
        "dotisk_queries": dotisk,
        "niche_trend": {"points": _trend_points(),
                        "keywords": ["лазерна епіляція", "косметологія київ", "ботокс",
                                     "чистка обличчя", "мезотерапія"],
                        "geo": "UA", "change_pct": 40, "avg": 65.7, "peak": 82},
        "trend_svg": charts.trend_svg(_trend_points(), theme="dark"),
        "kwplan": _kwplan(),
        "kwplan_svg": charts.kwplan_svg(_kwplan()["trend"], _kwplan()["trend_labels"], theme="dark"),
        "ai_summary": {
            "checked": True,
            "summary": ("Сайт має сильну SEO-базу (24k трафіку, широка семантика) і високий потенціал у ТОП-1, "
                        "але конверсію стримує слабка hero-секція (CRO 42/100), а повторні продажі майже не "
                        "монетизуються. Найшвидша віддача — усунути мовний попап і посилити CTA, паралельно "
                        "запустити retention-розсилки на наявну аудиторію."),
            "priorities": [
                {"title": "Виправити hero: H1 + CTA + мікроформа", "why": "найдешевший приріст конверсії (+30–50% сторінки), нічого не коштує у трафіку"},
                {"title": "Запустити email/Viber-розсилки на базу", "why": "LTV 7500 ₴/клієнт, повторні майже не використовуються — швидкі гроші"},
                {"title": "Довести комерційні запити до ТОП-1", "why": "+9.5k візитів/міс за наявної бази — головний драйвер трафіку"},
            ],
        },
        "ai_seo": {
            "checked": True,
            "verdict": "Потужна семантична база під медичну нішу, але контент головної не розкриває ключових комерційних інтентів і слабко оптимізований під локальні запити.",
            "strengths": ["Широка структура (2584 орг. ключі)", "Стабільне зростання трафіку 12 міс", "Є блог для інформаційних запитів"],
            "weaknesses": ["H1 без ціннісної пропозиції та ключового запиту", "Тонкий SEO-текст на головній", "Мета-описи не під усі категорії послуг"],
            "gaps": ["Немає окремих сторінок під послуги+місто", "Бракує сторінок цін/акцій під транзакційні запити", "Відсутні FAQ під інформаційні запити"],
            "recommendations": ["Переписати H1/Title з вигодою + гео", "Додати посадкові під топ-послуги", "Розширити SEO-текст головної до 500+ симв. з LSI"],
        },
        "cro": _cro_demo(),
        "retention": {
            "checked": True, "avg_check": 2500, "avg_margin": 40,
            "repeat_rate": 50, "freq": 2.5, "life_months": 36,
            "ltv_revenue": 22500, "ltv_profit": 9000, "first_profit": 1000,
            "upside_per_customer": 8000, "monthly_customers": 340,
            "monthly_extra_profit": 34000, "annual_extra_profit": 408000, "uplift_pct": 15,
            "audience": {"ig_followers": 3120, "monthly_traffic": 24304},
            "signals": [
                {"name": "Захоплення email / розсилка", "present": False},
                {"name": "Онлайн-чат / месенджер", "present": True},
                {"name": "Програма лояльності / бонуси", "present": False},
                {"name": "Мобільний застосунок", "present": False},
                {"name": "Блог / контент для nurturing", "present": True},
            ],
            "channels": [
                "Email-флоу: welcome, кинутий кошик, пост-продаж, реактивація (win-back)",
                "Telegram / Viber-розсилки та бот для повторних записів",
                "Ретаргетинг на власну базу (Google/Meta) — догрів і крос-сейл",
                "Програма лояльності / бонуси (висока частота у ніші)",
            ],
            "quick_wins": [
                "Немає захоплення email на сайті — втрачається база для розсилок",
                "Велика IG-аудиторія (~3120) не конвертується у власну email-базу",
                "Немає програми лояльності за частих повторних візитів",
            ],
        },
        "ads": ads, "shopping": shopping, "meta_ads": meta_ads, "paid": paid, "social": social,
        "services": services, "factors": factors, "cases": cases,
        "reasons": [],
        "onpage": None, "contractor": None,
        "is_demo": True,
    }
