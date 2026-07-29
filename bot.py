"""Telegram-бот: аналіз домену під офер 'SEO з оплатою за вихід у ТОП'.
Меню, вибір регіону та глибини, inline-кнопки, обмеження доступу."""
import os, re, asyncio, html, logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile)
from aiogram.filters import CommandStart, Command

import qualify, config

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("seo-bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Обмеження доступу: список chat_id через кому (порожньо = дозволено всім)
ALLOWED = {int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x}
dp = Dispatcher()

EMOJI = {"green": "✅", "blue": "🔵", "amber": "🟡", "red": "⛔", "gray": "⚠️"}
REGIONS = {"ua": "🇺🇦 Україна", "pl": "🇵🇱 Польща", "de": "🇩🇪 Німеччина", "us": "🇺🇸 США"}

SETTINGS = {}   # chat_id -> {"db":"ua","depth":"full"}
LAST = {}       # chat_id -> {"domain":..., "res":...}

BTN_ANALYZE = "🔍 Аналіз сайту"
BTN_SETTINGS = "⚙️ Налаштування"
BTN_CRIT = "ℹ️ Критерії"


def st(chat_id: int) -> dict:
    return SETTINGS.setdefault(chat_id, {"db": config.SEMRUSH_DB, "depth": "full"})


def allowed(chat_id: int) -> bool:
    return not ALLOWED or chat_id in ALLOWED


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_ANALYZE)],
                  [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_CRIT)]],
        resize_keyboard=True, input_field_placeholder="Надішли домен, напр. daydrive.ua")


def settings_kb(s: dict) -> InlineKeyboardMarkup:
    reg_row = [InlineKeyboardButton(
        text=("• " if s["db"] == code else "") + name, callback_data=f"reg:{code}")
        for code, name in REGIONS.items()]
    depth_row = [
        InlineKeyboardButton(text=("• " if s["depth"] == "full" else "") + "Повний (+on-page)",
                             callback_data="depth:full"),
        InlineKeyboardButton(text=("• " if s["depth"] == "fast" else "") + "Швидкий",
                             callback_data="depth:fast"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[reg_row[:2], reg_row[2:], depth_row])


def result_kb(res: dict) -> InlineKeyboardMarkup:
    rows = []
    # великі виділені кнопки переходу в бібліотеки реклами
    ad = res.get("ads") or {}
    if ad.get("link"):
        rows.append([InlineKeyboardButton(text="🔎 GOOGLE ADS TRANSPARENCY", url=ad["link"])])
    mt = res.get("meta_ads") or {}
    if mt.get("link"):
        rows.append([InlineKeyboardButton(text="📘 META AD LIBRARY", url=mt["link"])])
    if res.get("dotisk_queries"):
        rows.append([InlineKeyboardButton(text="🎯 Усі запити для дотиску", callback_data="allq")])
    rows.append([InlineKeyboardButton(text="📄 Завантажити PDF", callback_data="pdf")])
    rows.append([InlineKeyboardButton(text="🔁 Повторити", callback_data="again"),
                 InlineKeyboardButton(text="🆕 Нова перевірка", callback_data="newcheck")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def extract_domain(text: str) -> str:
    m = re.search(r"([a-z0-9\-]+\.)+[a-z]{2,}", (text or "").lower())
    return m.group(0) if m else ""


_BLOCKS = " ▏▎▍▌▋▊▉█"


def _fmtk(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1000:.1f}k".replace(".0k", "k")
    return str(n)


def _bar(n, mx, width=13) -> str:
    if mx <= 0:
        return ""
    units = n / mx * width
    full = int(units)
    s = "█" * full
    if full < width:
        s += _BLOCKS[min(8, int((units - full) * 8 + 0.5))]
    return s


def _num(n) -> str:
    return f"{int(n or 0):,}".replace(",", " ")


def _month(ym) -> str:
    ym = str(ym or "")
    return f"{ym[4:6]}.{ym[2:4]}" if len(ym) >= 6 else (ym or "—")


def _short_url(url) -> str:
    u = re.sub(r"^https?://", "", url or "").replace("www.", "")
    i = u.find("/")
    return (u[i:] if i >= 0 else "/") or "/"


def _matrix_pre(seg: dict) -> str:
    s = seg.get("segments") or {}
    L = seg.get("labels") or {}
    order = ["top3", "p4_10", "p11_20", "p21_50", "p51_100"]
    mx = max((s.get(k, 0) for k in order), default=0) or 1
    rows = []
    for k in order:
        n = s.get(k, 0)
        rows.append(f"{L.get(k, k):<6} {_bar(n, mx):<13} {_fmtk(n):>5}")
    return "<pre>" + html.escape("\n".join(rows)) + "</pre>"


def _traffic_pre(hist: list) -> str:
    pts = [h for h in list(reversed(hist))[-12:] if h.get("date")]
    vals = [max(0, int(h.get("org_traffic", 0) or 0)) for h in pts]
    if len(vals) < 2 or max(vals) <= 0:
        return ""
    mx = max(vals) or 1
    rows = [f"{_month(h.get('date')):<6} {_bar(v, mx):<13} {_fmtk(v):>6}"
            for h, v in zip(pts, vals)]
    chg = round((vals[-1] - vals[0]) / vals[0] * 100) if vals[0] > 0 else None
    chg_s = f" ({'+' if chg >= 0 else ''}{chg}%)" if chg is not None else ""
    head = f"📈 <b>Трафік за 12 міс:</b> {_fmtk(vals[0])}→{_fmtk(vals[-1])}{chg_s}"
    return head + "\n<pre>" + html.escape("\n".join(rows)) + "</pre>"


_SPARK = "▁▂▃▄▅▆▇█"


def _sparkline(vals, mx) -> str:
    if not vals or mx <= 0:
        return ""
    return "".join(_SPARK[min(7, int(v / mx * 7))] for v in vals)


def _pt_month(p: dict) -> str:
    """MM.YY з точки тренду (спершу timestamp, потім label)."""
    ts = p.get("ts")
    try:
        import datetime
        d = datetime.datetime.fromtimestamp(int(ts))
        return f"{d.month:02d}.{str(d.year)[2:]}"
    except Exception:
        lb = str(p.get("label") or "")
        m = re.search(r"(\d{4})", lb)
        return (lb[:5] if lb else "—")


def _trend_pre(nt: dict) -> str:
    pts = (nt or {}).get("points") or []
    if len(pts) < 3:
        return ""
    # ~7 рівномірних точок з підписом місяця (щоб було читабельно)
    k = 7
    n = len(pts)
    idx = sorted(set(round(i * (n - 1) / (k - 1)) for i in range(k)))
    sample = [pts[i] for i in idx]
    vals = [max(0.0, float(p.get("value", 0) or 0)) for p in sample]
    mx = max(vals) or 1
    rows = [f"{_pt_month(p):<6} {_bar(v, mx):<13} {int(round(v)):>3}"
            for p, v in zip(sample, vals)]
    chg = nt.get("change_pct")
    chg_s = f" ({'+' if chg >= 0 else ''}{chg}%)" if chg is not None else ""
    kw = " · ".join(nt.get("keywords") or [])
    out = (f"📊 <b>Тренд попиту</b> (Google Trends · 12 міс · UA · індекс 0–100):{chg_s}"
           f"\n<pre>{html.escape(chr(10).join(rows))}</pre>")
    if kw:
        out += f"<i>за запитами: {html.escape(kw)}</i>"
    return out


def _kwplan_pre(kp: dict) -> str:
    if not kp or not kp.get("trend"):
        return ""
    pts = kp["trend"]
    labels = kp.get("trend_labels") or []
    mx = max(pts) or 1
    # ~7 рівномірних точок з підписом місяця
    k = 7
    n = len(pts)
    idx = sorted(set(round(i * (n - 1) / (k - 1)) for i in range(k)))
    chart_rows = [f"{(labels[i] if i < len(labels) else '—'):<6} {_bar(pts[i], mx):<13} {_fmtk(pts[i]):>6}"
                  for i in idx]
    chg = kp.get("change_pct")
    chg_s = f" ({'+' if chg >= 0 else ''}{chg}%)" if chg is not None else ""
    top = kp.get("keywords") or []
    kw_rows = "\n".join(f"• {html.escape(k['keyword'])} — {_fmtk(k['volume'])}/міс"
                        for k in top[:5])
    out = (f"🔑 <b>Попит за запитами</b> (Keyword Planner · 12 міс · UA):{chg_s}"
           f"\n<pre>{html.escape(chr(10).join(chart_rows))}</pre>")
    if kw_rows:
        out += kw_rows
    return out


def _forecast_pre(hist: list, target) -> str:
    """Прогноз зростання: 3 останні фактичні міс + 4 прогнозовані до цілі."""
    import charts
    pts = [h for h in list(reversed(hist))[-3:] if h.get("date")]
    vals = [max(0, int(h.get("org_traffic", 0) or 0)) for h in pts]
    tgt = int(target or 0)
    if not vals or tgt <= vals[-1]:
        return ""
    base, gap = vals[-1], tgt - vals[-1]
    fvals = [int(round(base + gap * cf)) for cf in charts.FORECAST_CURVE]
    flabels = [charts._add_months(pts[-1].get("date"), j)
               for j in range(1, len(charts.FORECAST_CURVE) + 1)]
    mx = max(vals + fvals) or 1
    rows = [f"{_month(h.get('date')):<6} {_bar(v, mx):<13} {_fmtk(v):>6}"
            for h, v in zip(pts, vals)]
    rows.append("── прогноз ──")
    rows += [f"{_month(d):<6} {_bar(v, mx):<13} {_fmtk(v):>6}»"
             for d, v in zip(flabels, fvals)]
    head = f"📈 <b>Прогноз зростання трафіку</b> (ціль 4 міс: {_fmtk(fvals[-1])}/міс)"
    return head + "\n<pre>" + html.escape("\n".join(rows)) + "</pre>"


def _potential_pre(bn: dict) -> str:
    mul = f" ×{bn['multiplier']}" if bn.get("multiplier") else ""
    rows = [f"{'Трафік':<9}{_fmtk(bn['traffic_now'])} → {_fmtk(bn['traffic_top1'])}"
            f"  (+{_fmtk(bn['uplift'])}{mul})"]
    if bn.get("conv_pct") and bn.get("sales_uplift") is not None:
        q = f" · якість {bn['conv_quality_pct']}%" if bn.get("conv_quality_pct") is not None else ""
        close = f" · заявка→продаж {bn['close_pct']}%" if bn.get("close_pct") else ""
        rows.append(f"{'Заявки':<9}+{_num(bn['apps_uplift'])}/міс   (конв {bn['conv_pct']}%{q})")
        rows.append(f"{'Продажі':<9}+{_num(bn['sales_uplift'])}/міс{close}")
        rows.append(f"{'Дохід':<9}+{_num(bn['revenue_uplift'])} ₴   (чек {_num(bn['avg_check'])} ₴)")
        if bn.get("profit_uplift") and bn.get("avg_margin"):
            rows.append(f"{'Прибуток':<9}+{_num(bn['profit_uplift'])} ₴   (маржа {bn['avg_margin']}%)")
    if bn.get("modeled"):
        head = f"💰 <b>Потенціал</b> · ~{bn['queries']} комерц. запитів ТОП 4–20 (модель) → ТОП-1:"
    else:
        head = f"💰 <b>Потенціал</b> · усі {bn['queries']} комерц. запити ТОП 4–20 → ТОП-1:"
    return head + "\n<pre>" + html.escape("\n".join(rows)) + "</pre>"


def _mediaplan_pre(mp: dict) -> str:
    if not mp:
        return ""
    rows = [
        f"{'Бюджет':<9}{_fmtk(mp['budget'])} ₴/міс",
        f"{'Кліки':<9}{_fmtk(mp['clicks'])}   (CPC {mp['cpc']} ₴)",
        f"{'Заявки':<9}{_fmtk(mp['leads'])}   (конв {mp['conv_pct']}%)",
        f"{'Продажі':<9}{_fmtk(mp['sales'])}" + (f"   (→продаж {mp['close_pct']}%)" if mp.get('close_pct') else ""),
        f"{'Дохід':<9}{_fmtk(mp['revenue'])} ₴/міс",
    ]
    kpi = []
    if mp.get("net_profit") is not None:
        kpi.append(f"прибуток {_fmtk(mp['net_profit'])} ₴")
    if mp.get("romi") is not None:
        kpi.append(f"ROMI {mp['romi']}%")
    if mp.get("roas") is not None:
        kpi.append(f"ROAS {mp['roas']}×")
    if mp.get("cpl"):
        kpi.append(f"CPL {_fmtk(mp['cpl'])} ₴")
    if mp.get("cpa"):
        kpi.append(f"CPA {_fmtk(mp['cpa'])} ₴")
    if mp.get("drr") is not None:
        kpi.append(f"ДРР {mp['drr']}%")
    head = f"💸 <b>Медіаплан контексту</b> (бюджет {_fmtk(mp['budget'])} ₴):"
    out = head + "\n<pre>" + html.escape("\n".join(rows)) + "</pre>"
    if kpi:
        out += "<b>" + " · ".join(kpi) + "</b>"
    return out


def _pages_msg(res: dict) -> str:
    pages = res.get("top_pages_traffic") or []
    if not pages:
        return ""
    rows = [f"{'Сторінка':<24}{'зап':>4}{'4-20':>5}{'тр.':>7}{'потен':>7}"]
    for p in pages[:15]:
        rows.append(f"{_short_url(p.get('url'))[:24]:<24}{p.get('keywords', 0):>4}"
                    f"{p.get('q_4_20', 0):>5}{_fmtk(p.get('traffic', 0)):>7}"
                    f"{_fmtk(p.get('traffic_pot', 0)):>7}")
    head = f"📄 <b>ТОП-{min(len(pages), 15)} сторінок по трафіку — {html.escape(res['domain'])}</b>"
    return head + "\n<pre>" + html.escape("\n".join(rows)) + "</pre>"


def _dotisk_pre(dq: list, limit: int = 8) -> str:
    """Таблиця кандидатів у ТОП-1: запит · позиція · частотність · трафік у ТОП-1."""
    if not dq:
        return ""
    rows = [f"{'Запит':<20}{'поз':>4}{'частота':>8}{'ТОП1/міс':>9}"]
    for q in dq[:limit]:
        kw = str(q.get("keyword") or "")[:20]
        rows.append(f"{kw:<20}{q.get('position', 0):>4}"
                    f"{_fmtk(q.get('volume', 0)):>8}{_fmtk(q.get('traffic_top1', 0)):>9}")
    return "<pre>" + html.escape("\n".join(rows)) + "</pre>"


def fmt(res: dict) -> str:
    if res.get("error"):
        return f"⚠️ <b>{html.escape(res['domain'])}</b>\nПомилка: {html.escape(res['error'])}"
    lines = []
    cl = res.get("client") or {}
    if cl.get("is_client"):
        warn = ("вже клієнт Elit-Web" if cl.get("level") == "exact"
                else "є вірогідність, що сайт вже клієнт Elit-Web")
        m = f" (збіг: {html.escape(cl.get('matched'))})" if cl.get("matched") else ""
        lines.append(f"⚠️ <b>УВАГА:</b> {warn}{m}")
    lines += [f"{EMOJI.get(res['color'],'•')} <b>{html.escape(res['domain'])}</b> — {res['verdict']} (бал {res['score']})"]
    nz = res.get("niche") or {}
    if nz.get("subniche"):
        lines.append(f"🧭 <b>Ніша:</b> {html.escape(nz.get('direction_name') or '?')} → "
                     f"{html.escape(nz.get('industry_name') or '?')} → "
                     f"{html.escape(nz.get('subniche'))} <i>({nz.get('confidence')})</i>")
    if res.get("niche_caveat"):
        lines.append("⚠️ <i>Ніша не профільна під офер — умовно підходить, зважати на нішу</i>")
    if res.get("kw_caveat"):
        lines.append("⚠️ <i>Комерц. запитів 100–299 (нижче норми 300) — умовно прийнятно</i>")
    # --- динаміка трафіку (бар-чарт за 12 міс) ---
    tp = _traffic_pre(res.get("history") or [])
    if tp:
        lines.append("")
        lines.append(tp)
    trp = _trend_pre(res.get("niche_trend"))
    if trp:
        lines.append("")
        lines.append(trp)
    kpp = _kwplan_pre(res.get("kwplan"))
    if kpp:
        lines.append("")
        lines.append(kpp)
    # --- матриця позицій (бар-чарт) ---
    seg = res.get("segments") or {}
    if seg.get("total"):
        lines.append("")
        lines.append(f"📊 <b>Матриця позицій</b> ({_fmtk(seg['total'])} орг. ключів у ТОП-100):")
        lines.append(_matrix_pre(seg))
    # --- потенціал (воронка) ---
    bn = res.get("benefit") or {}
    if bn.get("queries"):
        lines.append("")
        lines.append(_potential_pre(bn))
        fp = _forecast_pre(res.get("history") or [], bn.get("traffic_top1"))
        if fp:
            lines.append("")
            lines.append(fp)
    ad = res.get("ads") or {}
    if ad.get("checked"):
        if ad.get("running"):
            adv = ""
            if ad.get("advertisers"):
                adv = " · " + html.escape(", ".join(ad["advertisers"]))
            per = f" за {ad['period_days']} дн." if ad.get("period_days") else ""
            lines.append(f"📣 <b>Контекст:</b> працює · ~{ad['count']} оголош.{per}{adv}")
            f = ad.get("formats") or {}
            if f:
                def _fm(name, n):
                    return f"{name} {n}" if n else f"{name} —"
                lines.append("   формати: "
                             + " · ".join([_fm("пошук", f.get("text", 0)),
                                           _fm("банери", f.get("image", 0)),
                                           _fm("відео", f.get("video", 0))]))
            pm = ad.get("platforms") or {}
            if pm:
                _sh = {"search": "Пошук", "youtube": "YouTube", "shopping": "Покупки",
                       "maps": "Карти", "play": "Play"}
                mxp = max(pm.values()) or 1
                prows = [f"{_sh[k]:<8}{_bar(pm.get(k, 0), mxp):<13}{pm.get(k, 0):>4}"
                         for k in ("search", "youtube", "shopping", "maps", "play")]
                lines.append("📊 <b>Платформи:</b>\n<pre>" + html.escape("\n".join(prows)) + "</pre>")
        else:
            per = f" за {ad['period_days']} дн." if ad.get("period_days") else ""
            lines.append(f"📣 <b>Контекст:</b> не крутиться{per}")
    mt = res.get("meta_ads") or {}
    if mt.get("checked"):
        if mt.get("running"):
            pl = mt.get("platforms") or {}
            def _pm(name, n):
                return f"{name} {n}" if n else None
            parts = [x for x in (_pm("FB", pl.get("facebook")), _pm("IG", pl.get("instagram")),
                                 _pm("Messenger", pl.get("messenger")), _pm("AN", pl.get("audience_network"))) if x]
            pstr = (" · " + ", ".join(parts)) if parts else ""
            pg = f" · «{html.escape(mt.get('page',''))}»" if mt.get("page") else ""
            lines.append(f"📘 <b>Meta реклама:</b> працює · {mt.get('count', 0)} активних крео{pg}{pstr}")
        else:
            lines.append("📘 <b>Meta реклама:</b> активних оголошень не знайдено")
    pd = res.get("paid") or {}
    if pd.get("budget") or pd.get("keywords"):
        b = f"~${pd['budget']}/міс" if pd.get("budget") else "н/д"
        lines.append(f"💵 <b>Бюджет контексту</b> (SemRush, оцінка): {b} · "
                     f"{pd.get('keywords', 0)} платних запитів")
    mp = res.get("media_plan")
    if mp:
        lines.append("")
        lines.append(_mediaplan_pre(mp))
    sc = res.get("social") or {}
    if sc.get("checked") and sc.get("found"):
        foll = sc.get("followers")
        foll = f"~{foll}" if foll is not None else "?"
        if sc.get("is_private"):
            lines.append(f"📱 <b>Instagram:</b> @{html.escape(sc.get('handle',''))} · приватний · "
                         f"{foll} підписн. — <a href=\"{sc['url']}\">профіль</a>")
        else:
            act = "активний" if sc.get("active") else "активність низька"
            lines.append(f"📱 <b>Instagram:</b> @{html.escape(sc.get('handle',''))} · {foll} підписн. · "
                         f"залуч. ~{sc.get('avg_engagement', 0)}/пост · {act} — "
                         f"<a href=\"{sc['url']}\">профіль</a>")
    elif sc.get("checked") and not sc.get("found"):
        lines.append("📱 <b>Instagram:</b> посилання на сайті не знайдено")
    sv = res.get("services") or []
    if sv:
        mk = {"yes": "✅", "maybe": "🟡", "no": "⛔"}
        lines.append("\n🧩 <b>Підходить під послуги:</b>")
        for s in sv:
            lines.append(f"{mk.get(s['level'], '•')} {html.escape(s['name'])} — {html.escape(s['note'])}")
    dq = res.get("dotisk_queries", [])
    if dq:
        lines.append(f"\n🎯 <b>Кандидати в ТОП-1</b> (топ {min(len(dq), 8)} з {len(dq)}):")
        lines.append(_dotisk_pre(dq, 8))
    return "\n".join(lines)


def _case_line(c: dict) -> str:
    lk = c.get("links", {})
    parts = []
    if lk.get("kp"): parts.append(f"<a href=\"{lk['kp']}\">КП</a>")
    if lk.get("ext"): parts.append(f"<a href=\"{lk['ext']}\">розшир.</a>")
    if lk.get("blog"): parts.append(f"<a href=\"{lk['blog']}\">стаття</a>")
    geo = f", {html.escape(c.get('country',''))}" if c.get("country") else ""
    return f"• {html.escape(c['domain'])} ({html.escape(c.get('service','')) }{geo}) — " + " · ".join(parts)


def fmt_cases(res: dict, chunk_limit: int = 3500) -> list:
    """Кейси окремими повідомленнями (щоб влізти в ліміт Telegram 4096)."""
    cs = res.get("cases") or []
    if not cs:
        return []
    header = f"📁 <b>Схожі кейси Elit-Web ({len(cs)}):</b>"
    msgs, cur = [], header
    for c in cs:
        line = _case_line(c)
        if len(cur) + len(line) + 1 > chunk_limit:
            msgs.append(cur)
            cur = ""
        cur += ("\n" if cur else "") + line
    if cur.strip():
        msgs.append(cur)
    return msgs


async def run_analysis(msg: Message, domain: str):
    s = st(msg.chat.id)
    wait = await msg.answer(
        f"🔎 Аналізую <b>{html.escape(domain)}</b> ({REGIONS.get(s['db'], s['db'])}, "
        f"{'повний' if s['depth']=='full' else 'швидкий'})… (10–30 c)", parse_mode="HTML")
    try:
        res = await asyncio.to_thread(qualify.qualify, domain, s["depth"] == "full", s["db"], True, True)
        LAST[msg.chat.id] = {"domain": domain, "res": res}
        try:
            import stats_log
            stats_log.log_analysis(res, "telegram", str(msg.chat.id))
        except Exception:
            pass
        await wait.edit_text(fmt(res), parse_mode="HTML", disable_web_page_preview=True,
                             reply_markup=result_kb(res))
        pm = _pages_msg(res)
        if pm:
            await msg.answer(pm, parse_mode="HTML", disable_web_page_preview=True)
        for cm in fmt_cases(res):
            await msg.answer(cm, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        log.exception("Analyze error for %s", domain)
        await wait.edit_text(f"⚠️ Помилка аналізу <b>{html.escape(domain)}</b>. Спробуй пізніше.",
                             parse_mode="HTML")


@dp.message(CommandStart())
async def start(msg: Message):
    if not allowed(msg.chat.id):
        return await msg.answer(f"⛔ Доступ обмежено. Твій chat_id: <code>{msg.chat.id}</code>", parse_mode="HTML")
    s = st(msg.chat.id)
    await msg.answer(
        "👋 <b>Аналіз інтернет-маркетингу сайту</b> — комплексна перевірка.\n\n"
        "Надішли <b>домен</b> — і я зберу по ньому:\n"
        "• 🔍 SEO-потенціал і кваліфікацію під офер «SEO за вихід у ТОП»\n"
        "• 📈 динаміку трафіку та прогноз зростання\n"
        "• 📊 попит у ніші (Google Trends) і за запитами (Keyword Planner)\n"
        "• 📣 контекстну рекламу (Google Ads Transparency) + медіаплан\n"
        "• 📘 таргет у Meta (Facebook / Instagram Ad Library)\n"
        "• 🧩 які послуги підходять + схожі кейси Elit-Web\n\n"
        f"Регіон: {REGIONS.get(s['db'], s['db'])} · Глибина: "
        f"{'повний' if s['depth']=='full' else 'швидкий'}\n"
        "Змінити — кнопка «⚙️ Налаштування».",
        parse_mode="HTML", reply_markup=main_kb())


@dp.message(Command("settings"))
@dp.message(F.text == BTN_SETTINGS)
async def settings_msg(msg: Message):
    if not allowed(msg.chat.id):
        return
    await msg.answer("⚙️ <b>Налаштування</b>\nОбери регіон бази SemRush і глибину аналізу:",
                     parse_mode="HTML", reply_markup=settings_kb(st(msg.chat.id)))


@dp.message(F.text == BTN_CRIT)
async def crit_msg(msg: Message):
    await msg.answer(
        "ℹ️ <b>Критерії кваліфікації</b>\n\n"
        f"• <b>Головний:</b> {config.COMMERCIAL_KW_MIN}+ комерц. запитів на позиціях "
        f"{config.POS_MIN}–{config.POS_MAX} — пул для вибору семантики клієнтом\n"
        f"• SEO-трафік ≥ {config.TRAFFIC_MIN}/міс\n"
        "• Ознаки SEO-оптимізації (якщо сайт недоступний — не враховується)\n"
        f"• Широка структура (≥ {config.STRUCTURE_KW_MIN} орг. ключів)",
        parse_mode="HTML")


@dp.message(F.text == BTN_ANALYZE)
async def ask_domain(msg: Message):
    if not allowed(msg.chat.id):
        return
    await msg.answer("Надішли домен, напр. <code>daydrive.ua</code>", parse_mode="HTML")


@dp.callback_query(F.data.startswith("reg:"))
async def cb_region(cb: CallbackQuery):
    code = cb.data.split(":", 1)[1]
    st(cb.message.chat.id)["db"] = code
    await cb.message.edit_reply_markup(reply_markup=settings_kb(st(cb.message.chat.id)))
    await cb.answer(f"Регіон: {REGIONS.get(code, code)}")


@dp.callback_query(F.data.startswith("depth:"))
async def cb_depth(cb: CallbackQuery):
    st(cb.message.chat.id)["depth"] = cb.data.split(":", 1)[1]
    await cb.message.edit_reply_markup(reply_markup=settings_kb(st(cb.message.chat.id)))
    await cb.answer("Глибину змінено")


@dp.callback_query(F.data == "allq")
async def cb_allq(cb: CallbackQuery):
    last = LAST.get(cb.message.chat.id)
    if not last or not last["res"].get("dotisk_queries"):
        return await cb.answer("Немає даних")
    dq = last["res"]["dotisk_queries"]
    header = f"🎯 <b>Усі кандидати в ТОП-1 — {html.escape(last['domain'])}</b> ({len(dq)})"
    # чанками по ~40 рядків, щоб влізти в ліміт Telegram
    for i in range(0, len(dq), 40):
        chunk = dq[i:i + 40]
        body = _dotisk_pre(chunk, len(chunk))
        head = header if i == 0 else ""
        await cb.message.answer((head + "\n" + body).strip(),
                                parse_mode="HTML", disable_web_page_preview=True)
    await cb.answer()


@dp.callback_query(F.data == "pdf")
async def cb_pdf(cb: CallbackQuery):
    last = LAST.get(cb.message.chat.id)
    if not last or not last.get("res"):
        return await cb.answer("Немає даних для звіту")
    await cb.answer("Готую PDF…")
    try:
        import pdf as pdfmod
        data = await asyncio.to_thread(pdfmod.build, last["res"])
        fname = (last["domain"] or "report").replace("/", "_") + "-elitweb.pdf"
        await cb.message.answer_document(
            BufferedInputFile(data, filename=fname),
            caption=f"📄 Звіт з аналізу — {html.escape(last['domain'])}")
    except Exception:
        log.exception("pdf failed for %s", last.get("domain"))
        await cb.message.answer("⚠️ Не вдалося згенерувати PDF. Спробуй пізніше.")


@dp.callback_query(F.data == "again")
async def cb_again(cb: CallbackQuery):
    last = LAST.get(cb.message.chat.id)
    if not last:
        return await cb.answer("Немає що повторити")
    await cb.answer("Повторюю…")
    await run_analysis(cb.message, last["domain"])


@dp.callback_query(F.data == "newcheck")
async def cb_newcheck(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "🆕 <b>Нова перевірка</b>\nНадішли домен, напр. <code>daydrive.ua</code>",
        parse_mode="HTML", reply_markup=main_kb())


@dp.message(F.text)
async def handle(msg: Message):
    if not allowed(msg.chat.id):
        return await msg.answer(f"⛔ Доступ обмежено. Твій chat_id: <code>{msg.chat.id}</code>", parse_mode="HTML")
    domain = extract_domain(msg.text)
    if not domain:
        return await msg.answer("Не бачу домену. Надішли, напр., <code>example.com</code>",
                                parse_mode="HTML", reply_markup=main_kb())
    await run_analysis(msg, domain)


async def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set (ENV).")
    bot = Bot(token=TOKEN)
    me = await bot.get_me()
    log.info("Bot started: @%s (id=%s). Polling...", me.username, me.id)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
