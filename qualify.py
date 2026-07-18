"""Логіка кваліфікації сайту під офер 'SEO з оплатою за вихід у ТОП'."""
from __future__ import annotations
import re
import config, semrush, onpage, clients, niche, cases, ads


def _brand_token(domain: str) -> str:
    host = re.sub(r"^https?://", "", domain).split("/")[0].replace("www.", "")
    token = host.split(".")[0]
    return token if len(token) >= 4 else ""


def _looks_category(url: str) -> bool:
    u = (url or "").lower()
    if not u:
        return False
    path = u.split("//", 1)[-1]
    path = path[path.find("/"):] if "/" in path else ""
    return path.strip("/") != ""


def _is_commercial(kw: dict, brand: str) -> bool:
    text = kw.get("keyword", "").lower()
    intent = kw.get("intent", "")
    url = (kw.get("url", "") or "").lower()
    if any(h in url for h in config.NON_COMMERCIAL_URL_HINTS):
        return False
    if intent == "2":
        return False
    if intent in config.COMMERCIAL_INTENTS:
        return True
    if any(p in text for p in config.COMMERCIAL_PATTERNS):
        return True
    if _looks_category(url):
        return True
    return False


def qualify(domain: str, do_onpage: bool = True, db: str = None,
            do_ads: bool = False) -> dict:
    if not config.SEMRUSH_API_KEY:
        raise RuntimeError("SEMRUSH_API_KEY не заданий (ENV).")

    domain = re.sub(r"^https?://", "", domain).strip("/ ").lower()
    brand = _brand_token(domain)
    client_info = clients.check(domain)

    overview = semrush.domain_overview(domain, db=db)
    kws = semrush.organic_keywords(domain, config.POS_MIN, config.POS_MAX,
                                   limit=config.KW_FETCH_LIMIT, db=db)
    commercial = [k for k in kws if _is_commercial(k, brand)]
    commercial_count = len(commercial)

    def push_score(k):
        pos = k.get("position") or 99
        vol = k.get("volume") or 0
        return vol / max(pos - 9, 1)
    dotisk = sorted(
        [k for k in commercial if (k.get("position") or 99) <= 20],
        key=push_score, reverse=True,
    )[:15]


    # --- потенційна вигода: топ-N запитів, трафік зараз vs у ТОП-1 ---
    def _ctr(p):
        return config.CTR_BY_POS.get(int(p or 99), config.CTR_FLOOR)
    top_q = sorted(commercial, key=lambda k: k.get("volume") or 0, reverse=True)[:config.BENEFIT_QUERIES]
    traf_now = sum((k.get("volume") or 0) * _ctr(k.get("position")) for k in top_q)
    traf_top1 = sum((k.get("volume") or 0) for k in top_q) * config.CTR_BY_POS[1]
    benefit = {
        "queries": len(top_q),
        "traffic_now": int(round(traf_now)),
        "traffic_top1": int(round(traf_top1)),
        "uplift": int(round(traf_top1 - traf_now)),
        "multiplier": round(traf_top1 / traf_now, 1) if traf_now > 0 else None,
    }

    onp = {"optimized": None, "reachable": None, "assessable": None, "status_note": None}
    if do_onpage:
        onp = onpage.analyze_site(domain)

    assessable = bool(onp.get("assessable")) if do_onpage else False

    # --- визначення ніші (евристика) ---
    _kw_text = " ".join(k.get("keyword", "") for k in kws)
    _onp_text = ""
    if isinstance(onp.get("home"), dict):
        h = onp["home"]
        _onp_text = " ".join([h.get("title", ""), h.get("description", ""), h.get("h1", "")])
    _cat_text = " ".join(c.get("url", "") for c in (onp.get("categories") or []) if isinstance(c, dict))
    niche_info = niche.classify(" ".join([domain, _kw_text, _onp_text, _cat_text]), onp)
    try:
        matched_cases = cases.match(niche_info, limit=config.CASES_LIMIT)
    except Exception:
        matched_cases = []

    # --- контекстна реклама (лише для одного домену; інформаційно) ---
    ads_info = None
    if do_ads:
        try:
            ads_info = ads.check(domain)
        except Exception:
            ads_info = {"checked": False, "note": "помилка перевірки"}

    pos = commercial_count                       # комерційні запити на 11-30
    traf = overview["organic_traffic"]
    c1 = pos >= config.COMMERCIAL_KW_MIN
    c2 = traf >= config.TRAFFIC_MIN
    # c3: True/False лише коли оцінка можлива; інакше None (не враховується)
    c3 = bool(onp.get("optimized")) if assessable else None
    c4 = (overview["organic_keywords"] >= config.STRUCTURE_KW_MIN)   # лише інформаційно

    # --- градація ---
    if pos == 0 or traf == 0:
        verdict, color = "НЕ ПІДХОДИТЬ", "red"          # немає позицій або трафіку взагалі
    elif c1 and c2:
        if c3 is False:
            verdict, color = "ДОБРЕ", "blue"            # все ок, крім оптимізації
        else:
            verdict, color = "ІДЕАЛЬНО", "green"        # усі фактори зійшлись
    else:
        verdict, color = "ПОСЕРЕДНЬО", "amber"          # є, але нижче наших норм

    _BASE = {"ІДЕАЛЬНО": 90, "ДОБРЕ": 70, "ПОСЕРЕДНЬО": 45, "НЕ ПІДХОДИТЬ": 10}
    score = _BASE[verdict] + round(min(pos / config.COMMERCIAL_KW_MIN, 1) * 9)
    score = min(score, 100)

    reasons = []
    reasons.append(("Комерц. запити для просування (11–30)",
                    f"{pos} / треба {config.COMMERCIAL_KW_MIN} — пул, з якого клієнт обирає семантику", c1))
    reasons.append(("SEO-трафік/міс",
                    f"{overview['organic_traffic']} / потрібно {config.TRAFFIC_MIN}", c2))
    if do_onpage:
        reasons.append(("Ознаки SEO-оптимізації", _onpage_summary(onp), c3))
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
            "opt_assessable": assessable,
            "opt_note": onp.get("status_note"),
            "reachable": onp.get("reachable"),
        },
        "client": client_info,
        "niche": niche_info,
        "cases": matched_cases,
        "benefit": benefit,
        "ads": ads_info,
        "reasons": reasons,
        "dotisk_queries": [
            {"keyword": k["keyword"], "position": k["position"],
             "volume": k["volume"], "cpc": k["cpc"], "url": k.get("url", "")}
            for k in dotisk
        ],
        "onpage": onp if do_onpage else None,
    }


def _onpage_summary(onp: dict) -> str:
    if not onp:
        return "—"
    if not onp.get("assessable"):
        return f"недоступно для оцінки ({onp.get('status_note') or 'причина невідома'})"
    return (f"мета ok: {onp.get('meta_pages_ok')}/{onp.get('checked_pages')}, "
            f"SEO-текст: {onp.get('seo_text_pages')}/{onp.get('checked_pages')}")
