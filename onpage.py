"""On-page SEO перевірка: заходить на сайт, дивиться title/description/h1
та наявність SEO-тексту на головній і кількох категоріях."""
from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import config

CATEGORY_HINTS = ("catalog", "category", "categories", "kategor", "/c/", "shop",
                  "products", "collection", "catalogue", "brand")


def _fetch(url: str):
    try:
        r = requests.get(url, timeout=config.HTTP_TIMEOUT,
                         headers={"User-Agent": config.USER_AGENT}, allow_redirects=True)
        if r.status_code >= 400:
            return None, f"HTTP {r.status_code}"
        return r.text, None
    except requests.RequestException as e:
        return None, str(e)[:120]


def _visible_text_len(soup: BeautifulSoup) -> int:
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return len(text)


def check_page(url: str) -> dict:
    html, err = _fetch(url)
    if err:
        return {"url": url, "error": err, "ok": False}
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = (desc_tag.get("content", "").strip() if desc_tag else "")
    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
    text_chars = _visible_text_len(soup)
    return {
        "url": url,
        "title": title, "title_len": len(title),
        "description": description, "desc_len": len(description),
        "h1": h1s[0] if h1s else "", "h1_count": len(h1s),
        "text_chars": text_chars,
        "has_seo_text": text_chars >= config.SEO_TEXT_MIN_CHARS,
        "meta_ok": bool(title) and bool(description) and len(h1s) >= 1,
        "ok": True,
    }


def _find_categories(base_url: str, html: str, limit: int = 3):
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc
    seen, cats = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        p = urlparse(href)
        if p.netloc != host:
            continue
        path = p.path.lower()
        if path in ("", "/"):
            continue
        if any(h in href.lower() for h in CATEGORY_HINTS):
            if href not in seen:
                seen.add(href); cats.append(href)
        if len(cats) >= limit:
            break
    # fallback: будь-які внутрішні посилання з глибиною >=1
    if len(cats) < limit:
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            p = urlparse(href)
            if p.netloc == host and p.path.count("/") >= 2 and href not in seen:
                seen.add(href); cats.append(href)
            if len(cats) >= limit:
                break
    return cats[:limit]


def analyze_site(domain: str) -> dict:
    """Повертає перевірку головної + до 3 категорій та зведення."""
    base = domain if domain.startswith("http") else "https://" + domain
    home_html, err = _fetch(base)
    if err:
        base_http = "http://" + domain if not domain.startswith("http") else base
        home_html, err = _fetch(base_http)
        if err:
            return {"reachable": False, "error": err, "home": None, "categories": []}
        base = base_http
    home = check_page(base)
    cats_urls = _find_categories(base, home_html, limit=3)
    cats = [check_page(u) for u in cats_urls]
    cat_ok = [c for c in cats if c.get("ok")]
    seo_text_pages = sum(1 for c in cat_ok if c.get("has_seo_text")) + (1 if home.get("has_seo_text") else 0)
    meta_pages = sum(1 for c in cat_ok if c.get("meta_ok")) + (1 if home.get("meta_ok") else 0)
    checked = 1 + len(cat_ok)
    # "оптимізований" = мета заповнені всюди + SEO-текст хоча б на половині
    optimized = (meta_pages == checked) and (seo_text_pages >= max(1, checked // 2))
    return {
        "reachable": True,
        "home": home,
        "categories": cats,
        "checked_pages": checked,
        "meta_pages_ok": meta_pages,
        "seo_text_pages": seo_text_pages,
        "optimized": optimized,
    }
