"""Аналіз соцмереж (Instagram) через SerpApi engine=instagram_profile.
Крок 1: тягнемо посилання на IG-профіль із головної сайту.
Крок 2: беремо підписників + залученість останніх постів.

ВАЖЛИВО: SerpApi не віддає дат постів, тому 'свіжість/періодичність' точно
не рахуємо — 'активність' оцінюємо м'яко за наявністю залученості.
Reach (охоплення) не публічний — використовуємо залученість (лайки+коменти)."""
from __future__ import annotations
import re
import requests
import config

SERPAPI_URL = "https://serpapi.com/search"

_IG_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I)
_RESERVED = {"p", "reel", "reels", "explore", "accounts", "tv", "stories", "about",
             "developer", "legal", "directory", "web", "sharer", "privacy", "terms",
             "instagram", "help", "press", "api"}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT,
                      "Accept-Language": config.ACCEPT_LANGUAGE})
    return s


def find_instagram(domain: str):
    """(handle|None, site_reachable). site_reachable=False, якщо сайт не відкрився."""
    host = re.sub(r"^https?://", "", (domain or "").strip().lower()).split("/")[0]
    sess = _session()
    reachable = False
    for url in (f"https://{host}", f"http://{host}"):
        try:
            r = sess.get(url, timeout=config.HTTP_TIMEOUT, allow_redirects=True)
            if r.status_code >= 400 or not r.text:
                continue
            reachable = True
            for m in _IG_RE.finditer(r.text):
                handle = m.group(1).strip("/.").lower()
                if handle and handle not in _RESERVED:
                    return handle, True
            return None, True
        except requests.RequestException:
            continue
    return None, reachable


def _profile(handle: str) -> dict:
    params = {"engine": "instagram_profile", "profile_id": handle,
              "api_key": config.SERPAPI_KEY}
    r = requests.get(SERPAPI_URL, params=params, timeout=config.ADS_TIMEOUT)
    return r.json()


def check(domain: str) -> dict:
    handle, site_reachable = find_instagram(domain)
    if not handle:
        return {"checked": True, "found": False, "site_reachable": site_reachable}

    url = f"https://www.instagram.com/{handle}/"
    if not config.SERPAPI_KEY:
        return {"checked": False, "found": True, "handle": handle, "url": url,
                "note": "SERPAPI_KEY не заданий"}
    try:
        data = _profile(handle)
    except Exception as e:
        return {"checked": False, "found": True, "handle": handle, "url": url,
                "note": f"помилка запиту: {str(e)[:120]}"}
    if data.get("error"):
        return {"checked": False, "found": True, "handle": handle, "url": url,
                "note": str(data["error"])[:160]}

    pr = data.get("profile_results") or {}
    posts = data.get("posts") or []
    followers = pr.get("followers")
    engs = []
    for p in posts:
        likes = p.get("liked_by_count") or p.get("media_preview_likes_count") or 0
        comments = p.get("comments_count") or 0
        engs.append(int(likes) + int(comments))
    avg_eng = round(sum(engs) / len(engs)) if engs else 0

    is_private = bool(pr.get("is_private"))
    # м'який проксі активності: приватний -> невідомо; є залученість -> активний
    if is_private:
        active = None
    else:
        active = bool(posts) and avg_eng > 0

    return {
        "checked": True, "found": True, "handle": handle, "url": url,
        "followers": followers,
        "is_private": is_private,
        "is_verified": bool(pr.get("is_verified")),
        "posts_sampled": len(posts),
        "avg_engagement": avg_eng,
        "active": active,
        "full_name": pr.get("full_name") or "",
    }
