"""Пороги кваліфікації та налаштування. Перевизначаються через ENV."""
import os

# --- AI-класифікатор ніші (Claude Haiku через Anthropic API) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NICHE_AI_MODEL = os.getenv("NICHE_AI_MODEL", "claude-haiku-4-5-20251001")
NICHE_AI_TIMEOUT = int(os.getenv("NICHE_AI_TIMEOUT", "20"))
# AI-аналітика (SEO-ревʼю + executive summary) — якісніша модель, on-demand.
AI_REVIEW_MODEL = os.getenv("AI_REVIEW_MODEL", "claude-sonnet-5")
AI_REVIEW_FALLBACK_MODEL = os.getenv("AI_REVIEW_FALLBACK_MODEL", "claude-haiku-4-5-20251001")
AI_REVIEW_TIMEOUT = int(os.getenv("AI_REVIEW_TIMEOUT", "60"))

# --- Google Ads API (Keyword Planner: домен -> запити + помісячний тренд обсягів) ---
# Безкоштовно (тарифікації викликів нема). Потрібні 5 значень нижче.
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID", "")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")  # MCC, 10 цифр без дефісів
GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "")             # акаунт для запиту (можна = MCC)
GOOGLE_ADS_API_VERSION = os.getenv("GOOGLE_ADS_API_VERSION", "v21")
KWPLAN_GEO = os.getenv("KWPLAN_GEO", "2804")        # 2804 = Україна (geoTargetConstants)
KWPLAN_LANG = os.getenv("KWPLAN_LANG", "1013")      # 1013 = укр., 1031 = рос. (languageConstants)
KWPLAN_LIMIT = int(os.getenv("KWPLAN_LIMIT", "15")) # скільки топ-запитів лишати у звіті
KWPLAN_TIMEOUT = int(os.getenv("KWPLAN_TIMEOUT", "30"))

# --- Retention-маркетинг (моделювання; зовнішніх API не потребує) ---
# Наскільки retention-програма підіймає захоплену частку повторного прибутку (частка від upside).
RETENTION_PROGRAM_UPLIFT = float(os.getenv("RETENTION_PROGRAM_UPLIFT", "0.15"))  # 15%

# --- CRO-аудитор (окремий сервіс Elit-Web, інтеграція через його API) ---
CRO_BASE_URL = os.getenv("CRO_BASE_URL", "https://cro-auditor-production.up.railway.app")
CRO_LOGIN_USER = os.getenv("CRO_LOGIN_USER", "")       # username для /api/login
CRO_LOGIN_PASSWORD = os.getenv("CRO_LOGIN_PASSWORD", "")
CRO_LANG = os.getenv("CRO_LANG", "ua")
CRO_TIMEOUT = int(os.getenv("CRO_TIMEOUT", "30"))       # логін
CRO_AUDIT_TIMEOUT = int(os.getenv("CRO_AUDIT_TIMEOUT", "150"))  # сам аудит (рендер сайту — довго)
CRO_ISSUES_LIMIT = int(os.getenv("CRO_ISSUES_LIMIT", "6"))      # скільки проблем виводити у звіт

# --- Логування аналізів у Google Таблицю (Apps Script веб-хук) ---
SHEETS_LOG_URL = os.getenv("SHEETS_LOG_URL", "")          # URL веб-застосунку Apps Script
SHEETS_LOG_SECRET = os.getenv("SHEETS_LOG_SECRET", "")    # опційний секрет (звірка у скрипті)
SHEETS_LOG_TIMEOUT = int(os.getenv("SHEETS_LOG_TIMEOUT", "10"))

# --- SemRush ---
SEMRUSH_API_KEY = os.getenv("SEMRUSH_API_KEY", "")
SEMRUSH_DB = os.getenv("SEMRUSH_DB", "ua")            # google.com.ua
SEMRUSH_BASE = "https://api.semrush.com/"

# --- Авторизація веб-інтерфейсу ---
APP_LOGIN_EMAIL = os.getenv("APP_LOGIN_EMAIL", "marketing@elit-web.ua")
APP_LOGIN_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "123456SM")
SECRET_KEY = os.getenv("SECRET_KEY", "elitweb-seo-qualifier-change-me-please")

# --- Telegram ---
TELEGRAM_BOT_URL = os.getenv("TELEGRAM_BOT_URL", "")   # напр. https://t.me/your_bot

# --- Контекстна реклама (SerpApi -> Google Ads Transparency Center) ---
# Перевіряється ЛИШЕ для одного домену (бот / поодинокий чек на вебі).
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
ADS_REGION = os.getenv("ADS_REGION", "2804")           # 2804 = Україна
ADS_TIMEOUT = int(os.getenv("ADS_TIMEOUT", "25"))
ADS_ACTIVE_DAYS = int(os.getenv("ADS_ACTIVE_DAYS", "7"))    # вікно даних Transparency Center (останні N днів)
ADS_CREATIVES_LIMIT = int(os.getenv("ADS_CREATIVES_LIMIT", "60"))  # скільки крео тягнути/виводити

# --- Meta (Facebook/Instagram) реклама через Apify Ad Library Scraper ---
# Deep-чек (1 домен). Актор і вхідні дані — через env, щоб міняти без коду.
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
APIFY_META_ACTOR = os.getenv("APIFY_META_ACTOR", "apify~facebook-ads-scraper")
# JSON-шаблон вхідних даних актора; {url} і {count} підставляються автоматично.
# Дефолт під apify/facebook-ads-scraper (поле urls + count + activeStatus).
APIFY_META_INPUT = os.getenv(
    "APIFY_META_INPUT",
    '{"startUrls":[{"url":"{url}"}],"count":{count},"activeStatus":"active"}')
APIFY_TIMEOUT = int(os.getenv("APIFY_TIMEOUT", "90"))        # таймаут актора (сек); з maxItems завершується швидше
META_ADS_LIMIT = int(os.getenv("META_ADS_LIMIT", "30"))      # кеп результатів для точного пошуку за FB-сторінкою
META_KEYWORD_LIMIT = int(os.getenv("META_KEYWORD_LIMIT", "10"))  # менший кеп для keyword-пошуку (чужі крео, дорого)
META_ADS_COUNTRY = os.getenv("META_ADS_COUNTRY", "ALL")   # ALL = усі країни (не відсікати таргет на інші гео)

# --- Соцмережі (Instagram через SerpApi) ---
# Поріг аудиторії, з якого SMM/таргет вважаємо доречним
SMM_FOLLOWERS_MIN = int(os.getenv("SMM_FOLLOWERS_MIN", "1000"))

# --- HubSpot (авто-оцінка діла через вебхук) ---
HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN", "")
HUBSPOT_API_BASE = os.getenv("HUBSPOT_API_BASE", "https://api.hubapi.com")
HUBSPOT_WEBHOOK_SECRET = os.getenv("HUBSPOT_WEBHOOK_SECRET", "")
# Обробляємо лише цю воронку (порожньо = усі). За замовч. — Elit-Web/DRP.
HUBSPOT_TEST_PIPELINE_ID = os.getenv("HUBSPOT_TEST_PIPELINE_ID", "3059032293")
HUBSPOT_DEAL_DOMAIN_PROP = os.getenv("HUBSPOT_DEAL_DOMAIN_PROP", "domain")
# Властивість діла для запису вердикту (порожньо = не писати)
HUBSPOT_VERDICT_PROP = os.getenv("HUBSPOT_VERDICT_PROP", "")
# Тягнути в оцінку контекст+соцмережі (SerpApi-квота). 0 = лише SemRush+onpage
HUBSPOT_ENRICH = os.getenv("HUBSPOT_ENRICH", "1") not in ("0", "false", "False", "")
# Автозаповнення полів-списків діла: Индустрия/Ниша/Подниша
HUBSPOT_SET_NICHE = os.getenv("HUBSPOT_SET_NICHE", "1") not in ("0", "false", "False", "")

# --- Manus (глибока якісна аналітика, асинхронно) ---
MANUS_API_KEY = os.getenv("MANUS_API_KEY", "")
MANUS_API_BASE = os.getenv("MANUS_API_BASE", "https://api.manus.ai/v2")
MANUS_AGENT_PROFILE = os.getenv("MANUS_AGENT_PROFILE", "manus-1.6")
MANUS_POLL_TIMEOUT = int(os.getenv("MANUS_POLL_TIMEOUT", "600"))   # макс. очікування, c
MANUS_POLL_INTERVAL = int(os.getenv("MANUS_POLL_INTERVAL", "15"))  # інтервал опитування, c
MANUS_HIDE_TASKS = os.getenv("MANUS_HIDE_TASKS", "0") in ("1", "true", "True")  # ховати в списку Manus
# Manus запускаємо лише для цих вердиктів
MANUS_VERDICTS = {"ІДЕАЛЬНО", "ДОБРЕ"}
# Telegram-токен для доставки результату у чат (для веб-сервісу)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# HUBSPOT_DEFINED association type: note -> deal (за замовч. 214)
HUBSPOT_NOTE_DEAL_ASSOC_ID = int(os.getenv("HUBSPOT_NOTE_DEAL_ASSOC_ID", "214"))

# --- Google-таблиця з поточними клієнтами (CSV) ---
CLIENTS_SHEET_CSV = os.getenv(
    "CLIENTS_SHEET_CSV",
    "https://docs.google.com/spreadsheets/d/1hm4at3Cbduf-tJcOP74O8A1aGAFIWLugTdqDhS4yZfo/gviz/tq?tqx=out:csv",
)
CASES_SHEET_CSV = os.getenv(
    "CASES_SHEET_CSV",
    "https://docs.google.com/spreadsheets/d/1ZlhfxFAqtqbR0uhPlhxywbkLAIhOnNDdi61JyBV-xdg/gviz/tq?tqx=out:csv",
)
CASES_LIMIT = int(os.getenv("CASES_LIMIT", "0"))   # 0 = усі кейси з посиланнями

# --- Пороги кваліфікації (з вимог) ---
POS_MIN = int(os.getenv("POS_MIN", "4"))
POS_MAX = int(os.getenv("POS_MAX", "20"))
COMMERCIAL_KW_MIN = int(os.getenv("COMMERCIAL_KW_MIN", "300"))
# М'який поріг: 100..299 комерц. запитів — умовно прийнятно (не рубаємо, але не «Ідеально»)
COMMERCIAL_KW_SOFT = int(os.getenv("COMMERCIAL_KW_SOFT", "100"))
TRAFFIC_MIN = int(os.getenv("TRAFFIC_MIN", "1000"))
# Потенціал зростання за трафіком: <MIN — не підходить; MIN..MID — середній; >MID — сильний
GROWTH_TRAFFIC_MIN = int(os.getenv("GROWTH_TRAFFIC_MIN", "1000"))
GROWTH_TRAFFIC_MID = int(os.getenv("GROWTH_TRAFFIC_MID", "10000"))
STRUCTURE_KW_MIN = int(os.getenv("STRUCTURE_KW_MIN", "1000"))
STRUCTURE_PAGES_MIN = int(os.getenv("STRUCTURE_PAGES_MIN", "150"))
KW_FETCH_LIMIT = int(os.getenv("KW_FETCH_LIMIT", "2000"))
# Скільки орг. позицій тягнути для матриці сегментів (Top3/4-10/11-20/21-50/51-100)
SEGMENT_FETCH_LIMIT = int(os.getenv("SEGMENT_FETCH_LIMIT", "5000"))
# Один об'єднаний витяг domain_organic (1–100) — з нього рахуємо матрицю,
# топ-сторінки і комерц. запити 4–20. Головний важіль вартості SemRush.
ORGANIC_FETCH_LIMIT = int(os.getenv("ORGANIC_FETCH_LIMIT", "200"))
SHOPPING_FETCH_LIMIT = int(os.getenv("SHOPPING_FETCH_LIMIT", "10"))   # PLA/Shopping-чек (30 юнітів/рядок)
PPC_BUDGET_DEFAULT = int(os.getenv("PPC_BUDGET_DEFAULT", "150000"))   # базовий бюджет медіаплану контексту, грн/міс
# Стеля коефіцієнта екстраполяції потенціалу на повну семантику (захист від «вибухів»)
MODEL_SCALE_CAP = float(os.getenv("MODEL_SCALE_CAP", "12"))
# Кеш даних SemRush по домену (сек). Повторний аналіз не робить нових запитів.
SEMRUSH_CACHE_TTL = int(os.getenv("SEMRUSH_CACHE_TTL", "604800"))

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

# --- CTR органічної видачі (позиція -> вірогідність кліку) ---
CTR_BY_POS = {
    1: 0.240, 2: 0.140, 3: 0.090, 4: 0.060, 5: 0.045, 6: 0.035, 7: 0.028,
    8: 0.022, 9: 0.017, 10: 0.013, 11: 0.010, 12: 0.0085, 13: 0.0075,
    14: 0.0065, 15: 0.0055, 16: 0.0048, 17: 0.0042, 18: 0.0036, 19: 0.0031, 20: 0.0027,
}
CTR_FLOOR = float(os.getenv("CTR_FLOOR", "0.002"))    # для позицій > 20
BENEFIT_QUERIES = int(os.getenv("BENEFIT_QUERIES", "20"))   # скільки топ-запитів беремо
HISTORY_MONTHS = int(os.getenv("HISTORY_MONTHS", "12"))     # глибина динаміки SEO/PPC (рік)
