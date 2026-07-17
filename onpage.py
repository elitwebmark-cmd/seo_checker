"""On-page SEO перевірка. Якщо сайт недоступний для оцінки (блок, robots,
JS-рендер тощо) — повертаємо assessable=False, і цей фактор не враховується."""
from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import config

CATEGORY_HINTS = ("catalog", "category", "categories", "kategor", "/c/", "shop",
                  "products", "collection", "catalogue", "brand")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": config.ACCEPT_LANGUAGE,
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _fetch(sess: requests.Session, url: str):
    """Повертає (text, status, code). status: ok | blocked | error."""
    last = None
    for _ in range(max(1, config.ONPAGE_RETRIES)):
        try:
            r = sess.get(url, timeout=config.HTTP_TIMEOUT, allow_redirects=True)
            if r.status_code in (401, 403, 429) or r.status_code == 503:
                return None, "blocked", r.status_code
            if r.status_code >= 400:
                return None, "error", r.status_code
            return r.text, "ok", r.status_code
        except requests.RequestException as e:
            last = str(e)[:120]
    return None, "error", last


def _robots_blocks_root(sess: requests.Session, base: str) -> bool:
    """True, якщо robots.txt забороняє корінь для нашого/усіх ботів."""
    try:
        r = sess.get(urljoin(base, "/robots.txt"), timeout=config.HTTP_TIMEOUT)
        if r.status_code != 200 or not r.text:
            return False
    except requests.RequestException:
        return False
    ua_applies = False
    disallow_root = False
    for raw in r.text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = [x.strip() for x in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            ua_applies = val == "*" or "seo-qualifier" in val.lower() or val.lower() in config.USER_AGENT.lower()
        elif key == "disallow" and ua_applies:
            if val == "/":
                disallow_root = True
    return disallow_root


def _visible_text_len(soup: BeautifulSoup) -> int:
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return len(text)


def check_page(sess, url: str) -> dict:
    html, status, code = _fetch(sess, url)
    if status != "ok":
        return {"url": url, "ok": False, "status": status, "code": code}
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = (desc_tag.get("content", "").strip() if desc_tag else "")
    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
    text_chars = _visible_text_len(BeautifulSoup(html, "html.parser"))
    script_srcs = len(soup.find_all("script", src=True))
    return {
        "url": url, "ok": True,
        "title": title, "title_len": len(title),
        "description": description, "desc_len": len(description),
        "h1": h1s[0] if h1s else "", "h1_count": len(h1s),
        "text_chars": text_chars, "script_srcs": script_srcs,
        "has_seo_text": text_chars >= config.SEO_TEXT_MIN_CHARS,
        "meta_ok": bool(title) and bool(description) and len(h1s) >= 1,
    }


def _find_categories(base_url: str, html: str, limit: int = 3):
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc
    seen, cats = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]); p = urlparse(href)
        if p.netloc != host or p.path in ("", "/"):
            continue
        if any(h in href.lower() for h in CATEGORY_HINTS) and href not in seen:
            seen.add(href); cats.append(href)
        if len(cats) >= limit:
            break
    if len(cats) < limit:
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"]); p = urlparse(href)
            if p.netloc == host and p.path.count("/") >= 2 and href not in seen:
                seen.add(href); cats.append(href)
            if len(cats) >= limit:
                break
    return cats[:limit]


def _unavailable(note: str) -> dict:
    return {"reachable": False, "assessable": False, "optimized": None,
            "status_note": note, "home": None, "categories": [],
            "checked_pages": 0, "meta_pages_ok": 0, "seo_text_pages": 0}


def analyze_site(domain: str) -> dict:
    sess = _session()
    base = domain if domain.startswith("http") else "https://" + domain

    if _robots_blocks_root(sess, base):
        return _unavailable("закрито в robots.txt")

    home_html, status, code = _fetch(sess, base)
    if status != "ok" and not domain.startswith("http"):
        home_html, status, code = _fetch(sess, "http://" + domain)
        if status == "ok":
            base = "http://" + domain
    if status == "blocked":
        return _unavailable(f"сайт блокує ботів (HTTP {code})")
    if status != "ok":
        return _unavailable(f"сайт недоступний ({code})")

    home = check_page(sess, base)
    # евристика JS-рендеру: майже нема тексту й тегів, але купа <script>
    if (home.get("text_chars", 0) < 150 and home.get("h1_count", 0) == 0
            and not home.get("title") and home.get("script_srcs", 0) >= 3):
        return _unavailable("ймовірно JS-рендер — недоступно для оцінки")

    cats = [check_page(sess, u) for u in _find_categories(base, home_html, limit=3)]
    cat_ok = [c for c in cats if c.get("ok")]
    checked = 1 + len(cat_ok)
    meta_pages = sum(1 for c in cat_ok if c.get("meta_ok")) + (1 if home.get("meta_ok") else 0)
    seo_text_pages = sum(1 for c in cat_ok if c.get("has_seo_text")) + (1 if home.get("has_seo_text") else 0)
    optimized = (meta_pages == checked) and (seo_text_pages >= max(1, checked // 2))
    return {
        "reachable": True, "assessable": True, "optimized": optimized,
        "status_note": "ok",
        "home": home, "categories": cats,
        "checked_pages": checked, "meta_pages_ok": meta_pages, "seo_text_pages": seo_text_pages,
    }
