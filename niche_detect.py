# -*- coding: utf-8 -*-
"""Легкий режим «тільки ніша»: домен -> ніша (без повного аналізу сайту).
Сигнали ті самі, що в qualify (топ-запити SemRush + мета сторінки), але без
економіки/реклами/CRO. Для пакетного дозаповнення ніш по списку доменів."""
from __future__ import annotations
import re, concurrent.futures
import config, semrush, niche
try:
    import onpage
except Exception:
    onpage = None


def _norm(d: str) -> str:
    d = re.sub(r"^https?://", "", str(d or "").strip().lower())
    d = d.split("/")[0].split("?")[0].strip().strip(".")
    return d


def detect(domain: str, db: str = None, use_onpage: bool = True, use_ai: bool = True) -> dict:
    dom = _norm(domain)
    if not dom or "." not in dom:
        return {"domain": domain, "subniche_code": None, "subniche": None,
                "industry_name": "Не домен", "confidence": "низька", "error": "не схоже на домен"}
    # 1) топ-запити SemRush (дешевий витяг)
    kws = []
    try:
        kws = semrush.organic_all(dom, db=db, limit=getattr(config, "NICHE_KW_LIMIT", 30))
    except Exception:
        kws = []
    kw_text = " ".join(k.get("keyword", "") for k in kws)
    kw_list = [k.get("keyword") for k in sorted(kws, key=lambda x: -(x.get("volume") or 0)) if k.get("keyword")][:12]
    # 2) мета сторінки (best-effort; на JS-захищених сайтах може не дати нічого)
    meta_text = ""; cat_text = ""; onp = None
    if use_onpage and onpage is not None:
        try:
            onp = onpage.analyze_site(dom)
            parts = []
            h = onp.get("home")
            if isinstance(h, dict):
                parts.append(h.get("niche_text") or " ".join([h.get("title", ""), h.get("description", ""), h.get("h1", "")]))
            for c in (onp.get("categories") or []):
                if isinstance(c, dict) and c.get("niche_text"):
                    parts.append(c["niche_text"])
            meta_text = " ".join(p for p in parts if p)
            cat_text = " ".join(c.get("url", "") for c in (onp.get("categories") or []) if isinstance(c, dict))
        except Exception:
            onp = None
    blob = " ".join([dom, (meta_text + " ") * 5, kw_text, cat_text])
    # 3) AI-класифікатор, фолбек на евристику (той самий шлях, що у qualify)
    ni = None; src = "heuristic"
    if use_ai:
        try:
            import niche_ai
            ni = niche_ai.classify_ai(dom, meta_text, kw_list)
            if ni and ni.get("subniche_code"):
                src = "ai"
        except Exception:
            ni = None
    if not ni or not ni.get("subniche_code"):
        ni = niche.classify(blob, onp); src = "heuristic"
    ni = dict(ni)
    ni["domain"] = dom
    ni["source"] = src
    ni["signals"] = (("запити" if kws else "") + ("+мета" if meta_text else "")) or "—"
    ni["n_kw"] = len(kws)
    return ni


def detect_many(domains, db: str = None, use_onpage: bool = True, use_ai: bool = True,
                workers: int = None) -> list:
    doms, seen = [], set()
    for d in domains:
        nd = _norm(d)
        key = nd or str(d).strip()
        if key and key not in seen:
            seen.add(key); doms.append(d)
    cap = getattr(config, "NICHE_BATCH_MAX", 60)
    doms = doms[:cap]
    w = workers or getattr(config, "NICHE_WORKERS", 6)
    out = [None] * len(doms)
    with concurrent.futures.ThreadPoolExecutor(max_workers=w) as ex:
        futs = {ex.submit(detect, d, db, use_onpage, use_ai): i for i, d in enumerate(doms)}
        for f in concurrent.futures.as_completed(futs):
            i = futs[f]
            try:
                out[i] = f.result()
            except Exception as e:
                out[i] = {"domain": doms[i], "subniche_code": None, "subniche": None,
                          "industry_name": "Помилка", "confidence": "низька", "error": str(e)[:120]}
    return out
