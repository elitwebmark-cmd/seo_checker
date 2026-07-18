"""Перевірка запущеної контекстної реклами через SerpApi
(Google Ads Transparency Center). Викликається ЛИШЕ для одного домену
(бот або поодинокий чек на вебі), бо це платний зовнішній виклик.

Повертає: чи крутиться реклама, приблизну кількість оголошень,
перелік рекламодавців і діплінк у Transparency Center."""
from __future__ import annotations
import re
import requests
import config

SERPAPI_URL = "https://serpapi.com/search"


def _host(domain: str) -> str:
    h = re.sub(r"^https?://", "", (domain or "").strip().lower())
    h = h.split("/")[0].strip("/ ")
    return h[4:] if h.startswith("www.") else h


def _deeplink(host: str) -> str:
    return f"https://adstransparency.google.com/?region=UA&domain={host}"


def check(domain: str) -> dict:
    host = _host(domain)
    link = _deeplink(host)
    if not config.SERPAPI_KEY:
        return {"checked": False, "note": "SERPAPI_KEY не заданий", "link": link}

    params = {
        "engine": "google_ads_transparency_center",
        "text": host,
        "region": config.ADS_REGION,   # 2804 = Україна
        "num": 40,
        "api_key": config.SERPAPI_KEY,
    }
    try:
        r = requests.get(SERPAPI_URL, params=params, timeout=config.ADS_TIMEOUT)
        data = r.json()
    except Exception as e:
        return {"checked": False, "note": f"помилка запиту: {str(e)[:120]}", "link": link}

    # SerpApi для «нема оголошень» повертає error-повідомлення — це валідний
    # результат «реклами не знайдено», а не збій перевірки.
    err = data.get("error")
    if err:
        low = err.lower()
        if "hasn't returned any results" in low or "no results" in low or "didn't return" in low:
            return {"checked": True, "running": False, "count": 0,
                    "advertisers": [], "link": link}
        return {"checked": False, "note": str(err)[:160], "link": link}

    creatives = data.get("ad_creatives") or []
    total = (data.get("search_information") or {}).get("total_results")
    count = int(total) if isinstance(total, (int, float)) and total else len(creatives)
    advertisers = []
    for c in creatives:
        a = (c.get("advertiser") or "").strip()
        if a and a not in advertisers:
            advertisers.append(a)
    running = count > 0 or bool(creatives)
    return {
        "checked": True,
        "running": running,
        "count": count,
        "advertisers": advertisers[:5],
        "link": link,
    }
