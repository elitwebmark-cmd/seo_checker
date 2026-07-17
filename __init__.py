"""Telegram-бот: надішли домен -> отримай висновок кваліфікації."""
import os, sys, re, asyncio, html
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from analyzer import qualify, config

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
dp = Dispatcher()

EMOJI = {"green": "✅", "amber": "🟡", "red": "⛔", "gray": "⚠️"}


def extract_domain(text: str) -> str:
    text = (text or "").strip()
    m = re.search(r"([a-z0-9\-]+\.)+[a-z]{2,}", text.lower())
    return m.group(0) if m else ""


def fmt(res: dict) -> str:
    if res.get("error"):
        return f"⚠️ <b>{html.escape(res['domain'])}</b>\nПомилка: {html.escape(res['error'])}"
    m = res.get("metrics", {})
    lines = [f"{EMOJI.get(res['color'],'•')} <b>{html.escape(res['domain'])}</b> — {res['verdict']} (бал {res['score']})", ""]
    for name, val, ok in res.get("reasons", []):
        mark = "✔" if ok else ("•" if ok is None else "✗")
        lines.append(f"{mark} {html.escape(name)}: <b>{html.escape(str(val))}</b>")
    dq = res.get("dotisk_queries", [])
    if dq:
        lines.append("\n🎯 <b>Кандидати в ТОП-1:</b>")
        for q in dq[:8]:
            lines.append(f"• {html.escape(q['keyword'])} — поз. {q['position']}, частотн. {q['volume']}")
    return "\n".join(lines)


@dp.message(CommandStart())
async def start(msg: Message):
    await msg.answer(
        "👋 Це аналізатор сайтів під офер <b>SEO з оплатою за вихід у ТОП</b>.\n\n"
        "Надішли домен (напр. <code>daydrive.ua</code>) — я перевірю по SemRush "
        "та on-page і скажу, чи підходить.\n\n"
        f"Головний критерій: {config.COMMERCIAL_KW_MIN}+ комерційних запитів на позиціях "
        f"{config.POS_MIN}–{config.POS_MAX}.",
        parse_mode="HTML")


@dp.message(F.text)
async def handle(msg: Message):
    domain = extract_domain(msg.text)
    if not domain:
        await msg.answer("Не бачу домену. Надішли, напр., <code>example.com</code>", parse_mode="HTML")
        return
    wait = await msg.answer(f"🔎 Аналізую <b>{html.escape(domain)}</b>… (10–30 c)", parse_mode="HTML")
    try:
        res = await asyncio.to_thread(qualify.qualify, domain, True)
        await wait.edit_text(fmt(res), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await wait.edit_text(f"⚠️ Помилка: {html.escape(str(e)[:300])}", parse_mode="HTML")


async def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не заданий (ENV).")
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
