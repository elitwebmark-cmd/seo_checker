"""Логіка кваліфікації сайту під офер 'SEO з оплатою за вихід у ТОП'."""
from __future__ import annotations
import re
from . import config, semrush, onpage


def _brand_token(domain: str) -> str:
    host = re.sub(r"^https?://", "", domain).split("/")[0]
    host = host.replace("www.", "")
    token = host.split(".")[0]
    return token if len(token) >= 4 else ""


def _looks_category(url: str) -> bool:
    """URL веде на категорію/товар магазину (є шлях, не корінь, не блог)."""
    u = (url or "").lower()
    if not u:
        return False
    path = u.split("//", 1)[-1]
    path = path[path.find("/"):] if "/" in path else ""
    return path.strip("/") != ""  # є непорожній шлях (блог/новини вже відсіяні окремо)


def _is_commercial(kw: dict, brand: str) -> bool:
    text = kw.get("keyword", "").lower()
    intent = kw.get("intent", "")
    url = (kw.get("url", "") or "").lower()
    # блог/новини/статті — не комерція
    if any(h in url for h in config.NON_COMMERCIAL_URL_HINTS):
        return False
    # чисто навігаційний (бренд) — не рахуємо
    if intent == "2":
        return False
    if brand and brand in text and intent == "2":
        return False
    # явно комерційний / транзакційний intent
    if intent in config.COMMERCIAL_INTENTS:
        return True
    # комерційні патерни у самому запиті
    if any(p in text for p in config.COMMERCIAL_PATTERNS):
        return True
    # informational intent, але веде на категорію/товар -> комерційний потенціал
    if _looks_category(url):
        return True
    return False


def qualify(domain: str, do_onpage: bool = True) -> dict:
    if not config.SEMRUSH_API_KEY:
        raise RuntimeError("SEMRUSH_API_KEY не заданий (ENV).")

    domain = re.sub(r"^https?://", "", domain).strip("/ ").lower()
    brand = _brand_token(domain)

    overview = semrush.domain_overview(domain)
    kws = semrush.organic_keywords(domain, config.POS_MIN, config.POS_MAX,
                                   limit=config.KW_FETCH_LIMIT)
    commercial = [k for k in kws if _is_commercial(k, brand)]
    commercial_count = len(commercial)

    # dotisk-кандидати: комерційні, ближче до ТОП-10, з великою частотністю
    def push_score(k):
        pos = k.get("position") or 99
        vol = k.get("volume") or 0
        return vol / max(pos - 9, 1)  # чим ближче до 10 і більший обсяг — тим вище
    dotisk = sorted(
        [k for k in commercial if (k.get("position") or 99) <= 20],
        key=push_score, reverse=True,
    )[:15]

    # on-page
    onp = {"optimized": None, "reachable": None}
    if do_onpage:
        onp = onpage.analyze_site(domain)

    # критерії
    c1 = commercial_count >= config.COMMERCIAL_KW_MIN            # головний
    c2 = overview["organic_traffic"] >= config.TRAFFIC_MIN
    c3 = bool(onp.get("optimized")) if do_onpage else None
    c4 = (overview["organic_keywords"] >= config.STRUCTURE_KW_MIN)

    # вердикт
    if not c1 or not c2:
        verdict = "НЕ ПІДХОДИТЬ"
        color = "red"
    elif do_onpage and c3 is False:
        verdict = "УМОВНО — потрібна дооптимізація"
        color = "amber"
    else:
        verdict = "ПІДХОДИТЬ"
        color = "green"

    # бал 0..100 (для сортування списку)
    score = 0
    score += min(commercial_count / config.COMMERCIAL_KW_MIN, 2) * 40   # до 80 (головний)
    score += min(overview["organic_traffic"] / config.TRAFFIC_MIN, 1) * 10
    score += (10 if c3 else 0) if do_onpage else 5
    score = round(min(score, 100))

    reasons = []
    reasons.append(("Комерційні поза ТОП-10 (11–30)",
                    f"{commercial_count} / потрібно {config.COMMERCIAL_KW_MIN}", c1))
    reasons.append(("SEO-трафік/міс",
                    f"{overview['organic_traffic']} / потрібно {config.TRAFFIC_MIN}", c2))
    if do_onpage:
        reasons.append(("Ознаки SEO-оптимізації",
                        _onpage_summary(onp), c3))
    reasons.append(("Широка структура (орг. ключів)",
                    f"{overview['organic_keywords']} / бажано {config.STRUCTURE_KW_MIN}", c4))

    return {
        "domain": domain,
        "verdict": verdict,
        "color": color,
        "score": score,
        "metrics": {
            "commercial_kw_11_30": commercial_count,
            "organic_traffic": overview["organic_traffic"],
            "organic_keywords": overview["organic_keywords"],
            "optimized": onp.get("optimized"),
            "reachable": onp.get("reachable"),
        },
        "reasons": reasons,
        "dotisk_queries": [
            {"keyword": k["keyword"], "position": k["position"],
             "volume": k["volume"], "cpc": k["cpc"], "url": k.get("url", "")}
            for k in dotisk
        ],
        "onpage": onp if do_onpage else None,
    }


def _onpage_summary(onp: dict) -> str:
    if not onp or onp.get("reachable") is False:
        return "сайт недоступний"
    return (f"мета ok: {onp.get('meta_pages_ok')}/{onp.get('checked_pages')}, "
            f"SEO-текст: {onp.get('seo_text_pages')}/{onp.get('checked_pages')}")
