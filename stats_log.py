# -*- coding: utf-8 -*-
"""Логування аналізів у Google Таблицю через Apps Script веб-хук.
Fire-and-forget: не блокує аналіз, помилки ковтає. Без SHEETS_LOG_URL — no-op."""
from __future__ import annotations
import time
import threading
import datetime
import requests
import config


def _row(res: dict, source: str, user: str = "") -> dict:
    ni = res.get("niche") or {}
    bn = res.get("benefit") or {}
    ov = res.get("overview") or {}
    return {
        "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "domain": res.get("domain", ""),
        "source": source,                      # web / telegram / demo / hubspot
        "user": user or "",                    # email або chat_id
        "region": res.get("db") or res.get("region") or "",
        "verdict": res.get("verdict", ""),
        "score": res.get("score", ""),
        "niche": ni.get("subniche", "") or "",
        "offer_fit": ("так" if ni.get("offer_fit") else "ні") if ni.get("offer_fit") is not None else "",
        "traffic": (ov.get("organic_traffic") if ov else "") or res.get("traffic", "") or "",
        "commercial_kw": bn.get("queries", "") if bn else "",
    }


def _post(payload: dict):
    url = config.SHEETS_LOG_URL
    if not url:
        return
    try:
        if config.SHEETS_LOG_SECRET:
            payload["secret"] = config.SHEETS_LOG_SECRET
        requests.post(url, json=payload, timeout=config.SHEETS_LOG_TIMEOUT)
    except Exception:
        pass


def log_analysis(res: dict, source: str, user: str = ""):
    """Асинхронно (в окремому потоці) пише рядок у таблицю."""
    if not config.SHEETS_LOG_URL or not res or res.get("error"):
        return
    try:
        payload = _row(res, source, user)
        threading.Thread(target=_post, args=(payload,), daemon=True).start()
    except Exception:
        pass
