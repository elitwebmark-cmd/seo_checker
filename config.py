"""Пороги кваліфікації та налаштування. Перевизначаються через ENV."""
import os

# --- SemRush ---
SEMRUSH_API_KEY = os.getenv("SEMRUSH_API_KEY", "")
SEMRUSH_DB = os.getenv("SEMRUSH_DB", "ua")            # google.com.ua
SEMRUSH_BASE = "https://api.semrush.com/"

# --- Авторизація веб-інтерфейсу ---
APP_LOGIN_EMAIL = os.getenv("APP_LOGIN_EMAIL", "marketing@elit-web.ua")
APP_LOGIN_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "123456ms")
SECRET_KEY = os.getenv("SECRET_KEY", "elitweb-seo-qualifier-change-me-please")

# --- Telegram ---
TELEGRAM_BOT_URL = os.getenv("TELEGRAM_BOT_URL", "")   # напр. https://t.me/your_bot

# --- Google-таблиця з поточними клієнтами (CSV) ---
CLIENTS_SHEET_CSV = os.getenv(
    "CLIENTS_SHEET_CSV",
    "https://docs.google.com/spreadsheets/d/1hm4at3Cbduf-tJcOP74O8A1aGAFIWLugTdqDhS4yZfo/gviz/tq?tqx=out:csv",
)
CASES_SHEET_CSV = os.getenv(
    "CASES_SHEET_CSV",
    "https://docs.google.com/spreadsheets/d/1ZlhfxFAqtqbR0uhPlhxywbkLAIhOnNDdi61JyBV-xdg/gviz/tq?tqx=out:csv",
)

# --- Пороги кваліфікації (з вимог) ---
POS_MIN = int(os.getenv("POS_MIN", "11"))
POS_MAX = int(os.getenv("POS_MAX", "30"))
COMMERCIAL_KW_MIN = int(os.getenv("COMMERCIAL_KW_MIN", "300"))
TRAFFIC_MIN = int(os.getenv("TRAFFIC_MIN", "500"))
STRUCTURE_KW_MIN = int(os.getenv("STRUCTURE_KW_MIN", "1000"))
STRUCTURE_PAGES_MIN = int(os.getenv("STRUCTURE_PAGES_MIN", "150"))
KW_FETCH_LIMIT = int(os.getenv("KW_FETCH_LIMIT", "2000"))

# Intent-коди SemRush: 0=Commercial, 1=Informational, 2=Navigational, 3=Transactional
COMMERCIAL_INTENTS = {"0", "3"}

COMMERCIAL_PATTERNS = [
    "купити", "купить", "ціна", "цена", "вартість", "стоимость", "замовити", "заказать",
    "недорого", "дешево", "прайс", "продаж", "продажа", "магазин", "доставка",
    "в наявності", "в наличии", "оптом", "розпродаж", "акція", "акции", "знижк",
]

# On-page
SEO_TEXT_MIN_CHARS = int(os.getenv("SEO_TEXT_MIN_CHARS", "500"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "12"))
ONPAGE_RETRIES = int(os.getenv("ONPAGE_RETRIES", "1"))

# Реалістичний браузерний User-Agent (щоб менше блокувань)
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
)
ACCEPT_LANGUAGE = os.getenv("ACCEPT_LANGUAGE", "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7")

NON_COMMERCIAL_URL_HINTS = [
    "/blog", "blog.", "/news", "/novosti", "/novyny", "/article", "/statya", "/stat",
    "/instruction", "/instructions", "/help", "/about", "/o-nas", "/compare",
    "/products/compare", "/review", "/otzyv", "/faq", "/wiki",
]
