# -*- coding: utf-8 -*-
"""Meta (Facebook/Instagram) реклама через Apify Ad Library Scraper.
Deep-чек (1 домен). Дістає: к-сть активних креативів, майданчики
(Facebook/Instagram/Messenger/Audience Network) і зображення креативів.

Актор і вхідні дані задаються через env (APIFY_META_ACTOR / APIFY_META_INPUT),
парсер полів толерантний до різних акторів. Таргетинг (аудиторії) Meta не
розкриває для комерційної реклами — показуємо лише крео/майданчики/к-сть."""
from __future__ import annotations
import re
import json
import urllib.parse
import requests
import config

_FB_RE = re.compile(r"facebook\.com/([A-Za-z0-9_.\-]{2,60})", re.I)
_FB_RESERVED = {"sharer", "plugins", "tr", "dialog", "events", "groups", "profile.php",
                "people", "pages", "watch", "story.php", "permalink.php", "help",
                "policies", "business", "login", "recover", "home.php", "photo.php",
                "hashtag", "search", "marketplace", "gaming", "ads"}


def _host(domain: str) -> str:
    h = re.sub(r"^https?://", "", (domain or "").strip().lower()).split("/")[0]
    return h[4:] if h.startswith("www.") else h


def find_facebook_page(domain: str):
    """Slug FB-сторінки з головної сайту (або None)."""
    host = _host(domain)
    headers = {"User-Agent": config.USER_AGENT, "Accept-Language": config.ACCEPT_LANGUAGE}
    for url in (f"https://{host}", f"http://{host}"):
        try:
            r = requests.get(url, headers=headers, timeout=config.HTTP_TIMEOUT, allow_redirects=True)
            if r.status_code >= 400 or not r.text:
                continue
            for m in _FB_RE.finditer(r.text):
                slug = m.group(1).strip("/.").lower()
                if slug and slug not in _FB_RESERVED and not slug.endswith(".php"):
                    return slug
            return None
        except requests.RequestException:
            continue
    return None


def _library_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return (f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
            f"&country={config.META_ADS_COUNTRY}&q={q}&search_type=keyword_unordered&media_type=all")


def _run_apify(url: str, count: int):
    tpl = config.APIFY_META_INPUT.replace("{url}", url).replace("{count}", str(count))
    try:
        payload = json.loads(tpl)
    except json.JSONDecodeError:
        payload = {"startUrls": [{"url": url}], "count": count}
    endpoint = (f"https://api.apify.com/v2/acts/{config.APIFY_META_ACTOR}"
                f"/run-sync-get-dataset-items"
                f"?token={config.APIFY_TOKEN}&timeout={config.APIFY_TIMEOUT}")
    r = requests.post(endpoint, json=payload, timeout=config.APIFY_TIMEOUT + 15)
    if r.status_code >= 400:
        raise RuntimeError(f"apify HTTP {r.status_code}: {r.text[:160]}")
    data = r.json()
    return data if isinstance(data, list) else (data.get("items") or [])


_PLAT_MAP = {
    "facebook": "facebook", "fb": "facebook",
    "instagram": "instagram", "ig": "instagram",
    "messenger": "messenger",
    "audience_network": "audience_network", "audience network": "audience_network",
    "an": "audience_network",
}


def _platforms_of(item: dict):
    for k in ("publisher_platforms", "publisherPlatforms", "platforms", "publisher_platform"):
        v = item.get(k)
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list) and v:
            return [str(x).lower().replace(" ", "_") for x in v]
    sn = item.get("snapshot") or {}
    v = sn.get("publisher_platform") or sn.get("publisherPlatforms")
    if isinstance(v, str):
        v = [v]
    if isinstance(v, list):
        return [str(x).lower().replace(" ", "_") for x in v]
    return []


def _images_of(item: dict):
    imgs = []
    sn = item.get("snapshot") or item.get("adSnapshot") or {}

    def _add(u):
        if u and isinstance(u, str) and u.startswith("http") and u not in imgs:
            imgs.append(u)

    for im in (sn.get("images") or item.get("images") or []):
        if isinstance(im, dict):
            _add(im.get("original_image_url") or im.get("resized_image_url") or im.get("url"))
        elif isinstance(im, str):
            _add(im)
    for c in (sn.get("cards") or []):
        if isinstance(c, dict):
            _add(c.get("original_image_url") or c.get("resized_image_url"))
    for v in (sn.get("videos") or []):
        if isinstance(v, dict):
            _add(v.get("video_preview_image_url") or v.get("thumbnail_url"))
    for k in ("originalImageUrl", "imageUrl", "thumbnailUrl", "image", "thumbnail"):
        _add(item.get(k))
    return imgs


def check(domain: str) -> dict:
    if not config.APIFY_TOKEN:
        return {"checked": False, "note": "APIFY_TOKEN не заданий"}
    page = find_facebook_page(domain)
    query = page or _host(domain).split(".")[0]
    lib_url = _library_url(query)
    try:
        items = _run_apify(lib_url, config.META_ADS_LIMIT)
    except Exception as e:
        return {"checked": False, "note": f"помилка Apify: {str(e)[:140]}", "link": lib_url}

    if not items:
        return {"checked": True, "running": False, "count": 0, "page": page,
                "platforms": {}, "creatives": [], "link": lib_url}

    plat = {"facebook": 0, "instagram": 0, "messenger": 0, "audience_network": 0}
    creatives, page_name = [], page
    for it in items:
        page_name = page_name or it.get("page_name") or it.get("pageName")
        seen = set()
        for p in _platforms_of(it):
            key = _PLAT_MAP.get(p)
            if key and key not in seen:
                plat[key] += 1
                seen.add(key)
        imgs = _images_of(it)
        if imgs and len(creatives) < 12:
            creatives.append({"image": imgs[0],
                              "link": (it.get("ad_snapshot_url") or it.get("snapshot_url")
                                       or (it.get("snapshot") or {}).get("snapshot_url") or lib_url),
                              "platforms": [k for k in seen]})
    return {
        "checked": True,
        "running": True,
        "count": len(items),
        "page": page_name or query,
        "platforms": plat,
        "creatives": creatives,
        "link": lib_url,
    }
