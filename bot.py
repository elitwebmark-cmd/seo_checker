"""Telegram-бот: аналіз домену під офер 'SEO з оплатою за вихід у ТОП'.
Меню, вибір регіону та глибини, inline-кнопки, обмеження доступу."""
import os, re, asyncio, html, logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton)
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


def result_kb(domain: str, has_dotisk: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_dotisk:
        rows.append([InlineKeyboardButton(text="🎯 Усі запити для дотиску", callback_data="allq")])
    rows.append([InlineKeyboardButton(text="🔁 Повторити", callback_data="again")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def extract_domain(text: str) -> str:
    m = re.search(r"([a-z0-9\-]+\.)+[a-z]{2,}", (text or "").lower())
    return m.group(0) if m else ""


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
    bn = res.get("benefit") or {}
    if bn.get("queries"):
        mul = f" · ×{bn['multiplier']}" if bn.get("multiplier") else ""
        lines.append(f"💰 <b>Потенціал</b> (топ-{bn['queries']} зап.): зараз ~{bn['traffic_now']}/міс → "
                     f"у ТОП-1 ~{bn['traffic_top1']}/міс (+{bn['uplift']}{mul})")
    ad = res.get("ads") or {}
    if ad.get("checked"):
        if ad.get("running"):
            adv = ""
            if ad.get("advertisers"):
                adv = " · " + html.escape(", ".join(ad["advertisers"]))
            lines.append(f"📣 <b>Контекст:</b> працює · ~{ad['count']} оголош.{adv} — "
                         f"<a href=\"{ad['link']}\">перевірити</a>")
        else:
            lines.append(f"📣 <b>Контекст:</b> не знайдено — <a href=\"{ad['link']}\">перевірити</a>")
    lines.append("")
    for name, val, ok in res.get("reasons", []):
        mark = "✔" if ok else ("•" if ok is None else "✗")
        lines.append(f"{mark} {html.escape(name)}: <b>{html.escape(str(val))}</b>")
    dq = res.get("dotisk_queries", [])
    if dq:
        lines.append("\n🎯 <b>Кандидати в ТОП-1:</b>")
        for q in dq[:8]:
            lines.append(f"• {html.escape(q['keyword'])} — поз. {q['position']}, частотн. {q['volume']}")
    cs = res.get("cases") or []
    if cs:
        lines.append("\n📁 <b>Схожі кейси Elit-Web:</b>")
        for c in cs[:4]:
            lk = c.get("links", {})
            parts = []
            if lk.get("kp"): parts.append(f"<a href=\"{lk['kp']}\">КП</a>")
            if lk.get("ext"): parts.append(f"<a href=\"{lk['ext']}\">розшир.</a>")
            if lk.get("blog"): parts.append(f"<a href=\"{lk['blog']}\">стаття</a>")
            geo = f", {html.escape(c.get('country',''))}" if c.get("country") else ""
            lines.append(f"• {html.escape(c['domain'])} ({html.escape(c.get('service','')) }{geo}) — " + " · ".join(parts))
    return "\n".join(lines)


async def run_analysis(msg: Message, domain: str):
    s = st(msg.chat.id)
    wait = await msg.answer(
        f"🔎 Аналізую <b>{html.escape(domain)}</b> ({REGIONS.get(s['db'], s['db'])}, "
        f"{'повний' if s['depth']=='full' else 'швидкий'})… (10–30 c)", parse_mode="HTML")
    try:
        res = await asyncio.to_thread(qualify.qualify, domain, s["depth"] == "full", s["db"], True)
        LAST[msg.chat.id] = {"domain": domain, "res": res}
        await wait.edit_text(fmt(res), parse_mode="HTML", disable_web_page_preview=True,
                             reply_markup=result_kb(domain, bool(res.get("dotisk_queries"))))
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
        "👋 Аналізатор сайтів під офер <b>SEO з оплатою за вихід у ТОП</b>.\n\n"
        "Надішли <b>домен</b> — я перевірю по SemRush та on-page і скажу, чи підходить.\n\n"
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
    lines = [f"🎯 <b>Усі кандидати в ТОП-1 — {html.escape(last['domain'])}</b>", ""]
    for q in dq:
        lines.append(f"• {html.escape(q['keyword'])} — поз. {q['position']}, частотн. {q['volume']}")
    await cb.message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
    await cb.answer()


@dp.callback_query(F.data == "again")
async def cb_again(cb: CallbackQuery):
    last = LAST.get(cb.message.chat.id)
    if not last:
        return await cb.answer("Немає що повторити")
    await cb.answer("Повторюю…")
    await run_analysis(cb.message, last["domain"])


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
