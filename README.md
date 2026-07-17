# elitweb · Кваліфікатор сайтів під офер «SEO з оплатою за вихід у ТОП»

Два інструменти на одному ядрі:
1. **Веб-інтерфейс** — вставляєш список сайтів (до 100), отримуєш вердикт по кожному.
2. **Telegram-бот** — надсилаєш домен, у відповідь — висновок.

## Що перевіряється (критерії)
| # | Критерій | Порог | Вага |
|---|----------|-------|------|
| 1 | Комерційні запити **поза ТОП-10** (позиції 11–30) | **≥ 300** | 🔴 головний |
| 2 | SEO-трафік / міс | ≥ 500 | важливий |
| 3 | Ознаки SEO-оптимізації (мета-теги + SEO-тексти на головній і категоріях) | є/нема | важливий |
| 4 | Широка структура (орг. ключів) | ≥ 1000 | середній |
| + | Кандидати в ТОП-1: комерційні з високою частотністю близько до ТОП-10 | топ-15 | бонус |

Джерела даних: запити/трафік — **SemRush Analytics API** (база `ua`); on-page — власний краулер (requests + BeautifulSoup). Комерційність визначається за **intent** SemRush (0=Commercial, 3=Transactional), брендові/навігаційні відсікаються.

## Структура
```
analyzer/    core: semrush.py, onpage.py, qualify.py, config.py
web/        Flask-застосунок (app.py + templates)
bot/        Telegram-бот (aiogram 3)
```

## Змінні середовища
Див. `.env.example`. Обов'язкові:
- `SEMRUSH_API_KEY` — ключ SemRush Analytics API.
- `TELEGRAM_BOT_TOKEN` — токен бота (лише для сервіса-бота).
Пороги (`COMMERCIAL_KW_MIN`, `TRAFFIC_MIN`, …) можна змінювати без правок коду.

## Локальний запуск
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заповни ключі
export $(grep -v '^#' .env | xargs)   # або використай python-dotenv

# веб
gunicorn web.app:app --bind 0.0.0.0:8080
# або: python web/app.py   → http://localhost:8080

# бот (окремо)
python -m bot.bot
```

## Деплой: GitHub → Railway
1. **GitHub:** створи репозиторій і залий цей код:
   ```bash
   git init && git add . && git commit -m "seo qualifier"
   git branch -M main
   git remote add origin https://github.com/<you>/elitweb-seo-qualifier.git
   git push -u origin main
   ```
2. **Railway → New Project → Deploy from GitHub repo** → обери репозиторій.
3. **Сервіс 1 (веб):** Railway підхопить `railway.json` (start = gunicorn). У *Variables* додай `SEMRUSH_API_KEY`, `SEMRUSH_DB=ua`. У *Settings → Networking → Generate Domain* — отримаєш URL.
4. **Сервіс 2 (бот):** у тому ж проєкті **New → GitHub Repo → той самий репозиторій**. У *Settings → Deploy → Custom Start Command* встав:
   ```
   python -m bot.bot
   ```
   У *Variables* додай `SEMRUSH_API_KEY`, `SEMRUSH_DB=ua`, `TELEGRAM_BOT_TOKEN`.
5. Готово: веб-сервіс має публічний URL, бот працює у режимі polling (домен не потрібен).

## Примітки
- Кожен домен = кілька запитів до SemRush API (витрачає API-units). Для списку зі 100 сайтів плануй ліміти.
- On-page-перевірку у веб-інтерфейсі можна вимкнути (чекбокс) для швидкості на великих списках.
- Дефолтні пороги — з ТЗ; змінюй через ENV під свою модель.
