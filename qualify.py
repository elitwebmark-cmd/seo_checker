"""Логіка кваліфікації сайту під офер 'SEO з оплатою за вихід у ТОП'."""
from __future__ import annotations
import re
import config, semrush, onpage, clients, niche, cases, ads, social


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
            do_ads: bool = False, do_social: bool = False) -> dict:
    if not config.SEMRUSH_API_KEY:
        raise RuntimeError("SEMRUSH_API_KEY не заданий (ENV).")

    domain = re.sub(r"^https?://", "", domain).strip("/ ").lower()
    brand = _brand_token(domain)
    client_info = clients.check(domain)

    overview = semrush.domain_overview(domain, db=db)
    try:
        history = semrush.domain_history(domain, db=db, limit=config.HISTORY_MONTHS)
    except Exception:
        history = []
    try:
        top_pages_traffic = semrush.top_pages(domain, overview["organic_traffic"], db=db, limit=10)
    except Exception:
        top_pages_traffic = []
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

    # --- ТОП сторінок по перспективі SEO (агрегація комерц. запитів 11-30 по URL) ---
    _page_agg = {}
    for k in commercial:
        u = k.get("url") or ""
        if not u:
            continue
        a = _page_agg.setdefault(u, {"url": u, "queries": 0, "traffic_now": 0.0, "traffic_top1": 0.0})
        a["queries"] += 1
        a["traffic_now"] += (k.get("volume") or 0) * _ctr(k.get("position"))
        a["traffic_top1"] += (k.get("volume") or 0) * config.CTR_BY_POS[1]
    top_pages_seo = sorted(_page_agg.values(), key=lambda x: x["traffic_top1"], reverse=True)[:10]
    for a in top_pages_seo:
        a["traffic_now"] = int(round(a["traffic_now"]))
        a["traffic_top1"] = int(round(a["traffic_top1"]))

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

    # --- соцмережі (Instagram; лише для одного домену; інформаційно) ---
    social_info = None
    if do_social:
        try:
            social_info = social.check(domain)
        except Exception:
            social_info = {"checked": False, "note": "помилка перевірки"}

    pos = commercial_count                       # комерційні запити на 11-30
    traf = overview["organic_traffic"]
    c1 = pos >= config.COMMERCIAL_KW_MIN
    c2 = traf >= config.TRAFFIC_MIN
    # c3: True/False лише коли оцінка можлива; інакше None (не враховується)
    c3 = bool(onp.get("optimized")) if assessable else None
    c4 = (overview["organic_keywords"] >= config.STRUCTURE_KW_MIN)   # лише інформаційно

    # потенціал зростання за трафіком (True сильний / None середній / False замало)
    if traf > config.GROWTH_TRAFFIC_MID:
        growth = True
    elif traf < config.GROWTH_TRAFFIC_MIN:
        growth = False
    else:
        growth = None
    growth_tier = "сильний" if growth is True else ("замало" if growth is False else "середній")

    niche_fit = niche_info.get("offer_fit")   # True підходить / False ні / None невідомо
    # Гейт нішею застосовуємо лише коли ніша визначена впевнено.
    # Якщо сайт блокує / мало даних (confidence "низька") — не рубаємо.
    niche_sure = niche_info.get("confidence") != "низька"
    niche_blocks = (niche_fit is False) and niche_sure
    if niche_fit is True:
        _niche_note, niche_ok = "підходить під офер", True
    elif niche_blocks:
        _niche_note, niche_ok = "не підходить під офер", False
    else:
        _niche_note, niche_ok = "не визначено впевнено — не враховано", None
    niche_note_full = f"{niche_info.get('subniche') or 'не визначено'} — {_niche_note}"

    # --- градація (три рівні: Ідеально / Добре / Не підходить) ---
    if niche_blocks:
        verdict, color = "НЕ ПІДХОДИТЬ", "red"          # ніша не підходить під офер
    elif c1 and c2 and growth is True and pos > 0 and traf > 0:
        if c3 is False:
            verdict, color = "ДОБРЕ", "blue"            # все ок, крім оптимізації
        else:
            verdict, color = "ІДЕАЛЬНО", "green"        # усі фактори зійшлись
    else:
        verdict, color = "НЕ ПІДХОДИТЬ", "red"          # будь-який фактор нижче норм

    _BASE = {"ІДЕАЛЬНО": 90, "ДОБРЕ": 70, "НЕ ПІДХОДИТЬ": 10}
    score = _BASE[verdict] + round(min(pos / config.COMMERCIAL_KW_MIN, 1) * 9)
    score = min(score, 100)

    services = _services(verdict, commercial_count, ads_info, social_info,
                         overview["organic_keywords"])

    reasons = []
    reasons.append(("Ніша під офер", niche_note_full, niche_ok))
    reasons.append(("Комерц. запити для просування (11–30)",
                    f"{pos} / треба {config.COMMERCIAL_KW_MIN} — пул, з якого клієнт обирає семантику", c1))
    reasons.append(("SEO-трафік/міс",
                    f"{overview['organic_traffic']} / потрібно {config.TRAFFIC_MIN}", c2))
    reasons.append(("Потенціал зростання (трафік/міс)", f"{traf} — {growth_tier}", growth))
    if do_onpage:
        reasons.append(("Ознаки SEO-оптимізації", _onpage_summary(onp), c3))
    reasons.append(("Широка структура (орг. ключів)",
                    f"{overview['organic_keywords']} / бажано {config.STRUCTURE_KW_MIN}", c4))

    # --- структуровані фактори для веб-інфографіки ---
    def _ratio(value, target):
        pct = round(min(value / target, 1) * 100) if target else 0
        mult = round(value / target, 1) if target and value >= target else None
        return pct, mult

    factors = []
    factors.append({"name": "Ніша під офер", "value": niche_note_full,
                    "ok": niche_ok, "kind": "status"})
    _p, _m = _ratio(pos, config.COMMERCIAL_KW_MIN)
    factors.append({"name": "Комерційні запити (11–30)", "value": pos,
                    "target": config.COMMERCIAL_KW_MIN, "ok": c1, "kind": "ratio",
                    "pct": _p, "mult": _m})
    _p, _m = _ratio(traf, config.TRAFFIC_MIN)
    factors.append({"name": "SEO-трафік / міс", "value": traf,
                    "target": config.TRAFFIC_MIN, "ok": c2, "kind": "ratio",
                    "pct": _p, "mult": _m})
    _gmax = config.GROWTH_TRAFFIC_MID * 2 or 1
    factors.append({"name": "Потенціал зростання", "value": traf, "ok": growth,
                    "kind": "growth", "tier": growth_tier,
                    "z1": round(config.GROWTH_TRAFFIC_MIN / _gmax * 100),
                    "z2": round(config.GROWTH_TRAFFIC_MID / _gmax * 100),
                    "marker": round(min(traf / _gmax, 1) * 100)})
    if do_onpage:
        factors.append({"name": "SEO-оптимізація", "value": _onpage_summary(onp),
                        "ok": c3, "kind": "status"})
    _p, _m = _ratio(overview["organic_keywords"], config.STRUCTURE_KW_MIN)
    factors.append({"name": "Широка структура (орг. ключів)", "value": overview["organic_keywords"],
                    "target": config.STRUCTURE_KW_MIN, "ok": c4, "kind": "ratio",
                    "pct": _p, "mult": _m})

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
        "history": history,
        "top_pages_traffic": top_pages_traffic,
        "top_pages_seo": top_pages_seo,
        "contractor": onp.get("contractor") if do_onpage else None,
        "ads": ads_info,
        "paid": {"keywords": overview.get("adwords_keywords", 0),
                 "traffic": overview.get("adwords_traffic", 0),
                 "budget": overview.get("adwords_cost", 0)},
        "social": social_info,
        "services": services,
        "factors": factors,
        "reasons": reasons,
        "dotisk_queries": [
            {"keyword": k["keyword"], "position": k["position"],
             "volume": k["volume"], "cpc": k["cpc"], "url": k.get("url", ""),
             "traffic_now": int(round((k.get("volume") or 0) * _ctr(k.get("position")))),
             "traffic_top1": int(round((k.get("volume") or 0) * config.CTR_BY_POS[1]))}
            for k in dotisk
        ],
        "onpage": onp if do_onpage else None,
    }


def _services(verdict, commercial_count, ads_info, social_info, organic_keywords=0) -> list:
    """Під які послуги потенційно підходить сайт. Евристика (level: yes|maybe|no)."""
    out = []

    # 1) SEO з оплатою за ТОП — з вердикту
    if verdict in ("ІДЕАЛЬНО", "ДОБРЕ"):
        out.append({"name": "SEO за ТОП", "level": "yes",
                    "note": "є комерційні позиції, трафік і потенціал під офер"})
    else:
        out.append({"name": "SEO за ТОП", "level": "no",
                    "note": "фактори нижче норм під офер"})

    # 1b) Базове (щомісячне) SEO — від наявної SEO-бази
    if organic_keywords >= config.STRUCTURE_KW_MIN or commercial_count > 0:
        out.append({"name": "Базове SEO", "level": "yes",
                    "note": "є SEO-база для щомісячного просування"})
    elif organic_keywords > 0:
        out.append({"name": "Базове SEO", "level": "maybe",
                    "note": "невелика SEO-база — потрібне доопрацювання"})
    else:
        out.append({"name": "Базове SEO", "level": "no",
                    "note": "немає SEO-присутності"})

    # 2) Контекстна реклама
    ads_running = bool(ads_info and ads_info.get("running"))
    if ads_running:
        out.append({"name": "Контекстна реклама", "level": "yes",
                    "note": "вже інвестує в контекст — можна вести/оптимізувати"})
    elif commercial_count >= 50:
        out.append({"name": "Контекстна реклама", "level": "yes",
                    "note": "є комерційна семантика — контекст доречний"})
    elif commercial_count > 0:
        out.append({"name": "Контекстна реклама", "level": "maybe",
                    "note": "мало комерційних запитів"})
    else:
        out.append({"name": "Контекстна реклама", "level": "no",
                    "note": "немає комерційних запитів"})

    # 3) SMM / таргет — лише якщо соцмережі перевіряли
    if social_info is not None:
        if not social_info.get("found"):
            out.append({"name": "SMM / таргет", "level": "maybe",
                        "note": "профіль не знайдено на сайті — потенціал з нуля"})
        elif not social_info.get("checked"):
            out.append({"name": "SMM / таргет", "level": "maybe",
                        "note": "профіль є, але дані недоступні"})
        else:
            f = social_info.get("followers") or 0
            if f >= config.SMM_FOLLOWERS_MIN:
                out.append({"name": "SMM / таргет", "level": "yes",
                            "note": f"є аудиторія (~{f} підписників) — SMM/таргет доречні"})
            else:
                out.append({"name": "SMM / таргет", "level": "maybe",
                            "note": f"профіль слабкий (~{f}) — треба розвивати"})

    return out


def _onpage_summary(onp: dict) -> str:
    if not onp:
        return "—"
    if not onp.get("assessable"):
        return f"недоступно для оцінки ({onp.get('status_note') or 'причина невідома'})"
    return (f"мета ok: {onp.get('meta_pages_ok')}/{onp.get('checked_pages')}, "
            f"SEO-текст: {onp.get('seo_text_pages')}/{onp.get('checked_pages')}")
