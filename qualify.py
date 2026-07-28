"""Логіка кваліфікації сайту під офер 'SEO з оплатою за вихід у ТОП'."""
from __future__ import annotations
import re, math
import config, semrush, onpage, clients, niche, cases, ads, social, charts


def _powerlaw_total(vols, target_count) -> float:
    """Оцінка сумарної частотності target_count запитів за степеневим (Zipf) хвостом,
    зафітованим по вибірці найчастотніших vols (голова). Повертає голову + хвіст."""
    vols = sorted([v for v in vols if v and v > 0], reverse=True)
    n = len(vols)
    head = float(sum(vols))
    if n < 5 or target_count <= n:
        return head
    v1, vn = vols[0], vols[-1]
    if v1 <= vn or vn <= 0:
        return head + (target_count - n) * (vn or 1) * 0.5
    b = math.log(v1 / vn) / math.log(n)
    b = min(max(b, 0.7), 3.0)          # тримаємо показник у притомних межах
    cap = min(int(target_count), n + 20000)
    tail = 0.0
    for r in range(n + 1, cap + 1):
        tail += v1 * (r ** (-b))
    return head + tail


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


# Вага конверсійності запиту (0..1): наскільки трафік з нього реально конвертує.
# Широкі напівінформаційні запити ("масаж", "диван") не мають задирати прогноз лідів.
_INTENT_WEIGHT = {"3": 1.0, "0": 0.75, "1": 0.25, "2": 0.15}


def _conv_weight(kw: dict) -> float:
    text = (kw.get("keyword", "") or "").lower().strip()
    intent = kw.get("intent", "")
    w = _INTENT_WEIGHT.get(intent, 0.5)
    has_buy = any(p in text for p in config.COMMERCIAL_PATTERNS)
    if has_buy:
        w = max(w, 0.95)
    elif len(text.split()) <= 1:          # широкий хед-запит без комерц. маркера
        w *= 0.4
    return max(0.05, min(w, 1.0))


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
    # ОДИН витяг domain_organic (1–100) — з нього рахуємо матрицю сегментів,
    # ТОП-сторінки і комерц. запити 4–20 (замість трьох окремих важких запитів).
    try:
        allkw = semrush.organic_all(domain, db=db)
    except Exception:
        allkw = []
    # Матриця сегментів — окремим дешевим запитом domain_rank (точний розподіл X0..XA).
    # Фолбек на розрахунок із витягу ключів, якщо розподіл недоступний.
    try:
        segments = semrush.position_distribution(domain, db=db)
    except Exception:
        segments = None
    if not (isinstance(segments, dict) and segments.get("total")):
        segments = semrush.segments_from(allkw, limit=config.ORGANIC_FETCH_LIMIT)
    top_pages_traffic = semrush.pages_from(allkw, limit=15)
    kws = [k for k in allkw if config.POS_MIN <= (k.get("position") or 0) <= config.POS_MAX]
    commercial = [k for k in kws if _is_commercial(k, brand)]

    # --- модель на всю семантику: тягнемо лише «голову» (найчастотніші запити),
    # а потенціал екстраполюємо на ПОВНУ к-сть запитів 4–20 (точну й безкоштовну
    # з розподілу X1+X2) за степеневим хвостом частотностей.
    _seg = (segments or {}).get("segments") or {}
    total_4_20 = int(_seg.get("p4_10", 0)) + int(_seg.get("p11_20", 0))
    n_all, n_comm = len(kws), len(commercial)
    model_scale, full_comm = 1.0, n_comm
    if total_4_20 > n_all and n_all >= 5 and n_comm >= 5:
        comm_frac = n_comm / n_all                     # частка комерційних у вибірці
        full_comm = max(n_comm, int(round(total_4_20 * comm_frac)))
        _cvols = [k.get("volume") or 0 for k in commercial]
        _head_vol = sum(_cvols) or 1
        model_scale = min(max(_powerlaw_total(_cvols, full_comm) / _head_vol, 1.0),
                          config.MODEL_SCALE_CAP)
    commercial_count = full_comm          # оцінка ПОВНОЇ к-сті комерц. запитів 4–20
    modeled = model_scale > 1.02

    def push_score(k):
        pos = k.get("position") or 99
        vol = k.get("volume") or 0
        return vol / max(pos - 3, 1)
    dotisk = sorted(
        [k for k in commercial if (k.get("position") or 99) <= 20],
        key=push_score, reverse=True,
    )[:15]

    # --- потенційна вигода: голова × модель на всю семантику, трафік зараз vs у ТОП-1 ---
    def _ctr(p):
        return config.CTR_BY_POS.get(int(p or 99), config.CTR_FLOOR)
    top_q = commercial   # голова; решту семантики додає model_scale
    traf_now = sum((k.get("volume") or 0) * _ctr(k.get("position")) for k in top_q) * model_scale
    traf_top1 = sum((k.get("volume") or 0) for k in top_q) * config.CTR_BY_POS[1] * model_scale
    benefit = {
        "queries": full_comm,
        "queries_sampled": n_comm,
        "modeled": modeled,
        "traffic_now": int(round(traf_now)),
        "traffic_top1": int(round(traf_top1)),
        "uplift": int(round(traf_top1 - traf_now)),
        "multiplier": round(traf_top1 / traf_now, 1) if traf_now > 0 else None,
    }

    # --- ТОП сторінок по перспективі SEO (агрегація комерц. запитів 4-20 по URL) ---
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

    # --- економіка потенціалу: прогноз лідів/продажів, доходу і прибутку з приросту трафіку ---
    _conv = niche_info.get("conv_pct")
    _check = niche_info.get("avg_check")
    _margin = niche_info.get("avg_margin")
    if _conv and _check and benefit.get("queries"):
        # комерційно-зважений трафік: широкі/напівінформаційні запити важать менше
        _ctr1 = config.CTR_BY_POS[1]
        w_now = w_t1 = 0.0
        for k in commercial:
            vol = k.get("volume") or 0
            w = _conv_weight(k)
            w_now += vol * _ctr(k.get("position")) * w
            w_t1 += vol * _ctr1 * w
        # екстраполяція на всю семантику (та сама модель, що й для трафіку)
        w_now *= model_scale
        w_t1 *= model_scale
        w_uplift = w_t1 - w_now
        # воронка: заявки -> продажі (× конверсія заявка->продаж) -> дохід -> прибуток
        _close = niche_info.get("close_pct")
        _cf = (_close / 100.0) if _close else 1.0
        _apps_up = w_uplift * _conv / 100.0          # заявки з приросту трафіку
        _apps_t1 = w_t1 * _conv / 100.0
        _sales_up = _apps_up * _cf                    # продажі
        _sales_t1 = _apps_t1 * _cf
        _rev_up = _sales_up * _check                  # валовий дохід
        _rev_t1 = _sales_t1 * _check
        # комерційна якість трафіку: частка зваженого приросту від «сирого»
        raw_uplift = benefit.get("uplift") or 0
        conv_quality = round(w_uplift / raw_uplift * 100) if raw_uplift > 0 else None
        benefit.update({
            "conv_pct": _conv,
            "avg_check": _check,
            "avg_margin": _margin,
            "close_pct": _close,
            "conv_type": niche_info.get("conv_type"),
            "conv_quality_pct": conv_quality,
            # інваріанти для онлайн-перерахунку воронки (зважений приріст трафіку)
            "w_uplift": int(round(w_uplift)),
            "w_t1": int(round(w_t1)),
            "apps_uplift": int(round(_apps_up)),
            "apps_top1": int(round(_apps_t1)),
            "sales_uplift": int(round(_sales_up)),
            "sales_top1": int(round(_sales_t1)),
            "revenue_uplift": int(round(_rev_up)),
            "revenue_top1": int(round(_rev_t1)),
            "leads_uplift": int(round(_apps_up)),   # alias (сумісність)
        })
        if _margin:
            benefit["profit_uplift"] = int(round(_rev_up * _margin / 100.0))
            benefit["profit_top1"] = int(round(_rev_t1 * _margin / 100.0))

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

    pos = commercial_count                       # комерційні запити на 4-20
    traf = overview["organic_traffic"]
    c1_full = pos >= config.COMMERCIAL_KW_MIN     # повна норма (300)
    c1_soft = pos >= config.COMMERCIAL_KW_SOFT    # умовно прийнятно (100–299)
    c1 = c1_full
    kw_caveat = c1_soft and not c1_full           # 100–299: не рубаємо, але не «Ідеально»
    c1_state = True if c1_full else (None if c1_soft else False)
    c2 = traf >= config.TRAFFIC_MIN
    # c3: True/False лише коли оцінка можлива; інакше None (не враховується)
    c3 = bool(onp.get("optimized")) if assessable else None
    c4 = (overview["organic_keywords"] >= config.STRUCTURE_KW_MIN)   # лише інформаційно

    # потенціал зростання за трафіком (True сильний / None середній / False замало)
    if traf >= config.GROWTH_TRAFFIC_MID:
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
    # Не підходить: трафік <5000 (growth False), нема позицій/трафіку,
    # або замало комерц. запитів / трафіку під норму.
    # Ніша сама по собі більше НЕ рубає лід: якщо всі критерії добрі, але ніша
    # не профільна — ставимо ДОБРЕ (умовно підходить, треба зважати на нішу).
    # Комерц. запити: <100 рубає; 100–299 умовно прийнятно (максимум ДОБРЕ); ≥300 повна норма.
    niche_caveat = False
    if growth is False or pos == 0 or traf == 0 or not (c1_soft and c2):
        verdict, color = "НЕ ПІДХОДИТЬ", "red"
    elif niche_blocks:
        # критерії пройдено, але ніша не профільна — умовно підходить
        verdict, color = "ДОБРЕ", "blue"
        niche_caveat = True
    elif growth is True and c3 is not False and c1_full:
        # сильний трафік (>10000) + оптимізація ок/недоступна + повна норма запитів
        verdict, color = "ІДЕАЛЬНО", "green"
    else:
        # трафік середній (1–10k), слабка оптимізація, або комерц. запити 100–299
        verdict, color = "ДОБРЕ", "blue"

    _BASE = {"ІДЕАЛЬНО": 90, "ДОБРЕ": 70, "НЕ ПІДХОДИТЬ": 10}
    score = _BASE[verdict] + round(min(pos / config.COMMERCIAL_KW_MIN, 1) * 9)
    score = min(score, 100)

    services = _services(verdict, commercial_count, ads_info, social_info,
                         overview["organic_keywords"], niche_caveat)

    reasons = []
    reasons.append(("Ніша під офер", niche_note_full, niche_ok))
    reasons.append(("Комерц. запити для просування (4–20)",
                    f"{pos} / норма {config.COMMERCIAL_KW_MIN} (умовно від {config.COMMERCIAL_KW_SOFT})"
                    + (" — умовно прийнятно" if kw_caveat else ""), c1_state))
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
    factors.append({"name": "Комерційні запити (4–20)", "value": pos,
                    "target": config.COMMERCIAL_KW_MIN, "ok": c1_state, "kind": "ratio",
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
        "niche_caveat": niche_caveat,
        "kw_caveat": kw_caveat,
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
        "segments": segments,
        "traffic_svg": charts.traffic_svg(history, months=config.HISTORY_MONTHS),
        "forecast_svg": charts.forecast_svg(history, benefit.get("traffic_top1"),
                                            theme="dark"),
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


def apply_custom_econ(benefit: dict, conv=None, check=None, margin=None, close=None) -> dict:
    """Перерахунок воронки за кастомними даними користувача.
    Спирається на збережені інваріанти w_uplift/w_t1 (зважений приріст трафіку).
    Порожні/None параметри беруться з поточних (нішевих) значень."""
    if not benefit:
        return benefit
    w_up = benefit.get("w_uplift")
    w_t1 = benefit.get("w_t1")
    if w_up is None or w_t1 is None:
        return benefit

    def _num(v, cur):
        try:
            return float(v) if v not in (None, "") else cur
        except (TypeError, ValueError):
            return cur

    conv = _num(conv, benefit.get("conv_pct"))
    check = _num(check, benefit.get("avg_check"))
    margin = _num(margin, benefit.get("avg_margin"))
    close = _num(close, benefit.get("close_pct"))
    if not conv or not check:
        return benefit

    cf = (close / 100.0) if close else 1.0
    apps_up = w_up * conv / 100.0
    apps_t1 = w_t1 * conv / 100.0
    sales_up = apps_up * cf
    sales_t1 = apps_t1 * cf
    rev_up = sales_up * check
    rev_t1 = sales_t1 * check
    benefit.update({
        "conv_pct": round(conv, 2),
        "avg_check": int(round(check)),
        "avg_margin": (round(margin, 1) if margin else margin),
        "close_pct": (round(close, 1) if close else close),
        "apps_uplift": int(round(apps_up)),
        "apps_top1": int(round(apps_t1)),
        "sales_uplift": int(round(sales_up)),
        "sales_top1": int(round(sales_t1)),
        "revenue_uplift": int(round(rev_up)),
        "revenue_top1": int(round(rev_t1)),
        "leads_uplift": int(round(apps_up)),
        "custom": True,
    })
    if margin:
        benefit["profit_uplift"] = int(round(rev_up * margin / 100.0))
        benefit["profit_top1"] = int(round(rev_t1 * margin / 100.0))
    else:
        benefit.pop("profit_uplift", None)
        benefit.pop("profit_top1", None)
    return benefit


def _services(verdict, commercial_count, ads_info, social_info, organic_keywords=0,
              niche_caveat=False) -> list:
    """Під які послуги потенційно підходить сайт. Евристика (level: yes|maybe|no)."""
    out = []

    # 1) SEO з оплатою за ТОП — з вердикту
    if niche_caveat:
        out.append({"name": "SEO за ТОП", "level": "maybe",
                    "note": "критерії ок, але ніша не профільна — умовно підходить, зважати на нішу"})
    elif verdict in ("ІДЕАЛЬНО", "ДОБРЕ"):
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
