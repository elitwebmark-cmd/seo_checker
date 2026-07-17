"""Пороги кваліфікації та налаштування. Перевизначаються через ENV."""
import os

# --- SemRush ---
SEMRUSH_API_KEY = os.getenv("SEMRUSH_API_KEY", "")
SEMRUSH_DB = os.getenv("SEMRUSH_DB", "ua")            # google.com.ua
SEMRUSH_BASE = "https://api.semrush.com/"

# --- Пороги кваліфікації (з вимог) ---
# 1) Комерційні запити поза ТОП-10 (позиції 11..POS_MAX) — НАЙВАЖЛИВІШЕ
POS_MIN = int(os.getenv("POS_MIN", "11"))
POS_MAX = int(os.getenv("POS_MAX", "30"))
COMMERCIAL_KW_MIN = int(os.getenv("COMMERCIAL_KW_MIN", "300"))
# 2) SEO-трафік / міс
TRAFFIC_MIN = int(os.getenv("TRAFFIC_MIN", "500"))
# 4) Широка структура (проксі: к-сть органічних ключів або сторінок)
STRUCTURE_KW_MIN = int(os.getenv("STRUCTURE_KW_MIN", "1000"))
STRUCTURE_PAGES_MIN = int(os.getenv("STRUCTURE_PAGES_MIN", "150"))

# Скільки ключів тягнути з SemRush (пейджинг по 1000)
KW_FETCH_LIMIT = int(os.getenv("KW_FETCH_LIMIT", "2000"))

# Intent-коди SemRush: 0=Commercial, 1=Informational, 2=Navigational, 3=Transactional
COMMERCIAL_INTENTS = {"0", "3"}

# Патерни комерційних запитів (fallback / підсилення)
COMMERCIAL_PATTERNS = [
    "купити", "купить", "ціна", "цена", "вартість", "стоимость", "замовити", "заказать",
    "недорого", "дешево", "прайс", "продаж", "продажа", "магазин", "доставка",
    "в наявності", "в наличии", "оптом", "розпродаж", "акція", "акции", "знижк",
]

# On-page
SEO_TEXT_MIN_CHARS = int(os.getenv("SEO_TEXT_MIN_CHARS", "500"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (compatible; elitweb-seo-qualifier/1.0; +https://elit-web.ua)",
)

# URL-и, що НЕ є комерційними (блог/новини/статті/довідка) — виключаємо
NON_COMMERCIAL_URL_HINTS = [
    "/blog", "blog.", "/news", "/novosti", "/novyny", "/article", "/statya", "/stat",
    "/instruction", "/instructions", "/help", "/about", "/o-nas", "/compare",
    "/products/compare", "/review", "/otzyv", "/faq", "/wiki",
]
