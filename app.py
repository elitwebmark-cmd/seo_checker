"""Веб-інтерфейс: авторизація -> список сайтів -> прогрес -> результати."""
# deploy marker: CRO integration + /debug/cro (rebuild trigger)
import os, uuid, threading, concurrent.futures, functools, time, logging
from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, session, Response)

import qualify, config, hubspot_sync, manus, semrush

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("seo-web")

app = Flask(__name__, template_folder=".")
app.secret_key = config.SECRET_KEY
MAX_DOMAINS = int(os.getenv("MAX_DOMAINS", "100"))
WORKERS = int(os.getenv("WORKERS", "6"))
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "240"))       # межа на весь джоб, c
DOMAIN_TIMEOUT = int(os.getenv("DOMAIN_TIMEOUT", "90"))  # орієнтир на 1 домен, c

JOBS = {}
JOBS_LOCK = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Якщо іконки залились у корінь репо (GitHub іноді розпласкує static/) —
# копіюємо їх у static/, щоб url_for('static', ...) працював.
try:
    os.makedirs(STATIC_DIR, exist_ok=True)
    for _fn in ("logo.png", "logo.svg", "ic-search.png", "ic-bot.png",
                "ic-monitor.png", "ic-trophy.png", "ic-chart.png",
                "ic-niche.png", "ic-key.png"):
        _root = os.path.join(BASE_DIR, _fn)
        _dst = os.path.join(STATIC_DIR, _fn)
        if os.path.exists(_root) and not os.path.exists(_dst):
            import shutil
            shutil.copy(_root, _dst)
except Exception:
    pass


def _find_asset(*names):
    for n in names:
        if os.path.exists(os.path.join(STATIC_DIR, n)):
            return n
    return None


@app.context_processor
def inject_assets():
    return {"assets": {
        "logo": _find_asset("logo.png", "logo.svg"),
        "ic_search": _find_asset("ic-search.png", "ic-search.svg"),
        "ic_bot": _find_asset("ic-bot.png", "ic-bot.svg"),
        "ic_monitor": _find_asset("ic-monitor.png", "ic-monitor.svg"),
        "ic_trophy": _find_asset("ic-trophy.png", "ic-trophy.svg"),
        "ic_chart": _find_asset("ic-chart.png", "ic-chart.svg"),
        "ic_niche": _find_asset("ic-niche.png", "ic-niche.svg"),
        "ic_key": _find_asset("ic-key.png", "ic-key.svg"),
    }}



# ---------- авторизація ----------
def login_required(f):
    @functools.wraps(f)
    def wrap(*a, **kw):
        if not session.get("auth"):
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrap


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pwd = request.form.get("password") or ""
        if email == config.APP_LOGIN_EMAIL.lower() and pwd == config.APP_LOGIN_PASSWORD:
            session["auth"] = True
            session["email"] = email
            return redirect(request.args.get("next") or url_for("index"))
        error = "Невірна пошта або пароль."
    return render_template("login.html", error=error, cfg=config)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- утиліти ----------
def _parse_domains(raw: str):
    items = []
    for line in (raw or "").replace(",", "\n").splitlines():
        d = line.strip().lower()
        if not d:
            continue
        d = d.replace("https://", "").replace("http://", "").strip("/ ")
        if d and d not in items:
            items.append(d)
    return items[:MAX_DOMAINS]


def _err(domain, note):
    return {"domain": domain, "verdict": "ПОМИЛКА", "color": "gray",
            "score": -1, "error": note, "reasons": [], "metrics": {},
            "dotisk_queries": []}


def _safe_qualify(domain, do_onpage, do_ads=False, do_social=False, do_cro=False):
    try:
        return qualify.qualify(domain, do_onpage=do_onpage, do_ads=do_ads,
                               do_social=do_social, do_cro=do_cro)
    except Exception as e:
        log.exception("qualify failed for %s", domain)
        return _err(domain, str(e)[:200])


def _finish(job_id):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if j and j["status"] != "done":
            j["results"].sort(key=lambda r: r.get("score", 0), reverse=True)
            j["status"] = "done"
            j["finished"] = time.time()
    log.info("job %s finished", job_id)


def _process_job(job_id, domains, do_onpage, do_ads=False, do_social=False, user="", do_cro=False):
    log.info("job %s START: %d domain(s), onpage=%s, ads=%s, social=%s, cro=%s",
             job_id, len(domains), do_onpage, do_ads, do_social, do_cro)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(_safe_qualify, d, do_onpage, do_ads, do_social, do_cro): d for d in domains}
            try:
                for fut in concurrent.futures.as_completed(futs, timeout=JOB_TIMEOUT):
                    d = futs[fut]
                    res = fut.result()
                    log.info("job %s: %s -> %s", job_id, d, res.get("verdict"))
                    try:
                        import stats_log
                        stats_log.log_analysis(res, "web", user, config.SEMRUSH_DB)
                    except Exception:
                        pass
                    with JOBS_LOCK:
                        j = JOBS.get(job_id)
                        if j is None:
                            return
                        j["results"].append(res)
                        j["done"] += 1
            except concurrent.futures.TimeoutError:
                # позначаємо незавершені як таймаут, щоб джоб не висів
                for fut, d in futs.items():
                    if not fut.done():
                        with JOBS_LOCK:
                            j = JOBS.get(job_id)
                            if j:
                                j["results"].append(_err(d, "таймаут аналізу"))
                                j["done"] += 1
                        log.warning("job %s: %s -> TIMEOUT", job_id, d)
    except Exception:
        log.exception("job %s crashed", job_id)
    finally:
        _finish(job_id)


def _prune_jobs():
    now = time.time()
    with JOBS_LOCK:
        for k in [k for k, v in JOBS.items()
                  if v.get("finished") and now - v["finished"] > 3600]:
            JOBS.pop(k, None)


# ---------- сторінки ----------
@app.route("/")
@login_required
def index():
    return render_template("index.html", cfg=config,
                           has_key=bool(config.SEMRUSH_API_KEY),
                           bot_url=config.TELEGRAM_BOT_URL)


@app.route("/demo")
@login_required
def demo():
    """Демо-результат на змодельованих даних — без витрати API-квоти."""
    import demo as demo_mod
    _prune_jobs()
    job_id = "demo" + uuid.uuid4().hex[:8]
    res = demo_mod.demo_result()
    now = time.time()
    with JOBS_LOCK:
        JOBS[job_id] = {"total": 1, "done": 1, "results": [res], "status": "done",
                        "do_onpage": True, "do_ads": True, "do_social": True,
                        "started": now, "finished": now, "demo": True}
    return redirect(url_for("results", job_id=job_id))


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    domains = _parse_domains(request.form.get("domains", ""))
    do_onpage = request.form.get("onpage") == "on"
    if not domains:
        return redirect(url_for("index"))
    # Реклама/соцмережі: лише коли домен один І галочку ввімкнено (економія квоти SerpApi)
    do_ads = (len(domains) == 1) and (request.form.get("ads") == "on")
    do_social = (len(domains) == 1) and (request.form.get("social") == "on")
    _prune_jobs()
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"total": len(domains), "done": 0, "results": [],
                        "status": "running", "do_onpage": do_onpage, "do_ads": do_ads,
                        "do_social": do_social, "started": time.time(), "finished": None}
    threading.Thread(target=_process_job,
                     args=(job_id, domains, do_onpage, do_ads, do_social,
                           session.get("email", "")),
                     daemon=True).start()
    return redirect(url_for("progress", job_id=job_id))


@app.route("/progress/<job_id>")
@login_required
def progress(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return redirect(url_for("index"))
    return render_template("progress.html", job_id=job_id, total=job["total"], cfg=config)


@app.route("/status/<job_id>")
@login_required
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"found": False})
        return jsonify({"found": True, "total": job["total"], "done": job["done"],
                        "status": job["status"]})


@app.route("/results/<job_id>")
@login_required
def results(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return redirect(url_for("index"))
    return render_template("results.html", results=job["results"], cfg=config,
                           do_onpage=job["do_onpage"], bot_url=config.TELEGRAM_BOT_URL,
                           job_id=job_id)


@app.route("/report/cro", methods=["POST", "GET"])
@login_required
def report_cro():
    """On-demand CRO-аудит по домену. Рендерить партіал і зберігає результат
    у job, щоб PDF теж міг його підхопити."""
    job_id = request.args.get("job", "")
    domain = (request.args.get("domain") or "").strip().lower()
    domain = domain.replace("https://", "").replace("http://", "").strip("/").split("/")[0]
    if not domain:
        return "<div class='cro-err'>Домен не вказано.</div>", 400
    try:
        import cro
        info = cro.audit(domain)
    except Exception:
        info = None
    if not info:
        return ("<div class='cro-err'>CRO-аудит недоступний: перевірте доступ (CRO_LOGIN_*) "
                "або спробуйте пізніше.</div>"), 200
    # зберегти в job, щоб /report.pdf теж включив CRO
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            for r in job["results"]:
                if r.get("domain") == domain:
                    r["cro"] = info
                    break
    return render_template("cro_block.html", cro=info)


@app.route("/report.pdf")
@login_required
def report_pdf():
    job_id = request.args.get("job", "")
    domain = (request.args.get("domain") or "").strip().lower()
    debug = request.args.get("debug")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    res = None
    if job:
        res = next((r for r in job["results"]
                    if (r.get("domain") or "").lower() == domain), None)
    # Демо-домен: завжди беремо змодельовані дані (без API-квоти).
    if (not res or res.get("error")) and domain:
        import demo as demo_mod
        if domain == demo_mod.DEMO_DOMAIN.lower():
            res = demo_mod.demo_result()
    # Fallback: job міг зникнути з пам'яті (рестарт контейнера). Перебудуємо
    # дані через qualify — SemRush-кеш (7 днів) робить це майже безкоштовним.
    if (not res or res.get("error")) and domain:
        rebuilt = _safe_qualify(domain, do_onpage=False, do_ads=True, do_social=True)
        if not rebuilt.get("error"):
            res = rebuilt
        elif debug:
            return Response("qualify fallback failed for %r:\n\n%s"
                            % (domain, rebuilt.get("error")),
                            mimetype="text/plain", status=500)
    if not res or res.get("error"):
        if debug:
            return Response("No result for domain=%r job=%r" % (domain, job_id),
                            mimetype="text/plain", status=404)
        return redirect(url_for("index"))
    # кастомні дані економіки з форми (щоб не мутувати збережений job — копіюємо)
    cust = {k: request.args.get(k) for k in ("conv", "check", "margin", "close")}
    if any(cust.values()) and res.get("benefit"):
        res = dict(res)
        res["benefit"] = dict(res["benefit"])
        qualify.apply_custom_econ(res["benefit"], cust["conv"], cust["check"],
                                  cust["margin"], cust["close"])
    # кастомний медіаплан контексту
    mpc = {k: request.args.get(k) for k in ("mp_budget", "mp_cpc", "mp_conv",
                                            "mp_check", "mp_margin", "mp_close")}
    if any(mpc.values()) and res.get("media_plan"):
        res = dict(res)
        base = res.get("media_plan") or {}

        def _pick(v, cur):
            return v if v not in (None, "") else cur
        rebuilt = qualify.build_media_plan(
            _pick(mpc["mp_budget"], base.get("budget")),
            _pick(mpc["mp_cpc"], base.get("cpc")),
            _pick(mpc["mp_conv"], base.get("conv_pct")),
            _pick(mpc["mp_check"], base.get("avg_check")),
            _pick(mpc["mp_margin"], base.get("avg_margin")),
            _pick(mpc["mp_close"], base.get("close_pct")))
        if rebuilt:
            res["media_plan"] = rebuilt
    try:
        import pdf
        data = pdf.build(res)
    except Exception:
        log.exception("pdf build failed for %s", domain)
        if debug:
            import traceback
            return Response("PDF build failed:\n\n" + traceback.format_exc(),
                            mimetype="text/plain", status=500)
        return "Помилка генерації PDF", 500
    fname = (domain or "report").replace("/", "_") + "-elitweb.pdf"
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.route("/api/analyze", methods=["POST"])
@login_required
def api_analyze():
    data = request.get_json(force=True, silent=True) or {}
    raw = data.get("domains")
    raw = "\n".join(raw) if isinstance(raw, list) else str(raw or "")
    domains = _parse_domains(raw)
    do_onpage = bool(data.get("onpage", True))
    do_ads = (len(domains) == 1) and bool(data.get("ads", True))
    do_social = (len(domains) == 1) and bool(data.get("social", True))
    out = []
    if domains:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(_safe_qualify, d, do_onpage, do_ads, do_social): d for d in domains}
            for fut in concurrent.futures.as_completed(futs):
                out.append(fut.result())
        out.sort(key=lambda r: r.get("score", 0), reverse=True)
    return jsonify({"results": out})


@app.route("/hooks/hubspot-deal", methods=["POST"])
def hubspot_deal_hook():
    # Захист: секрет з ?secret= або заголовка. Порожній секрет = endpoint закритий.
    secret = request.args.get("secret") or request.headers.get("X-Webhook-Secret", "")
    if not config.HUBSPOT_WEBHOOK_SECRET or secret != config.HUBSPOT_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    data = request.get_json(force=True, silent=True) or {}
    deal_id = hubspot_sync.extract_deal_id(data, request.args)
    if not deal_id:
        return jsonify({"ok": False, "error": "no deal id"}), 400
    # Діагностика: синхронний прогін із поверненням помилки (для налаштування)
    if request.args.get("debug") == "1":
        return jsonify(hubspot_sync.process_deal_debug(deal_id))
    # Відповідаємо миттєво, аналіз — у фоні (HubSpot чекає лише кілька секунд)
    threading.Thread(target=hubspot_sync.process_deal, args=(deal_id,), daemon=True).start()
    return jsonify({"ok": True, "deal_id": deal_id})


@app.route("/debug/meta")
def debug_meta():
    if request.args.get("secret") != config.HUBSPOT_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    domain = (request.args.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if not domain:
        return jsonify({"ok": False, "error": "no domain"}), 400
    try:
        import meta_ads
        data = meta_ads.check(domain, debug=True)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 500
    import json as _json
    return Response(_json.dumps(data, ensure_ascii=False, indent=2)[:12000],
                    mimetype="application/json")


@app.route("/debug/ads")
def debug_ads():
    if request.args.get("secret") != config.HUBSPOT_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    domain = (request.args.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if not domain:
        return jsonify({"ok": False, "error": "no domain"}), 400
    try:
        import ads as ads_mod
        data = ads_mod.debug(domain)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 500
    import json as _json
    return Response(_json.dumps(data, ensure_ascii=False, indent=2)[:14000],
                    mimetype="application/json")


@app.route("/debug/kwplan")
def debug_kwplan():
    if request.args.get("secret") != config.HUBSPOT_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    domain = (request.args.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if not domain:
        return jsonify({"ok": False, "error": "no domain"}), 400
    try:
        import kwplan
        data = kwplan.debug(domain)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 500
    import json as _json
    return Response(_json.dumps(data, ensure_ascii=False, indent=2)[:14000],
                    mimetype="application/json")


@app.route("/debug/cro")
def debug_cro():
    if request.args.get("secret") != config.HUBSPOT_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    domain = (request.args.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if not domain:
        return jsonify({"ok": False, "error": "no domain"}), 400
    try:
        import cro
        data = cro.debug(domain)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 500
    import json as _json
    return Response(_json.dumps(data, ensure_ascii=False, indent=2)[:14000],
                    mimetype="application/json")


@app.route("/hooks/manus-test")
def manus_test():
    # Тест Manus без діла: створює задачу по домену, повертає посилання на неї.
    if not config.MANUS_API_KEY:
        return jsonify({"ok": False, "error": "MANUS_API_KEY не заданий"}), 400
    if request.args.get("secret") != config.HUBSPOT_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    domain = (request.args.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if not domain:
        return jsonify({"ok": False, "error": "no domain"}), 400
    try:
        res = qualify.qualify(domain, do_onpage=False)
    except Exception as e:
        res = {"domain": domain, "verdict": "?", "metrics": {}, "niche": {}}
        log.warning("manus-test qualify failed: %s", e)
    try:
        task_id = manus.create_task(domain, res)
        return jsonify({"ok": True, "task_id": task_id,
                        "task_url": f"https://manus.im/app/{task_id}",
                        "verdict": res.get("verdict")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:400]})


@app.route("/traffic", methods=["POST"])
def traffic():
    # Пакетний збір органічного трафіку/ключів по списку доменів (серверний SemRush-ключ).
    if request.args.get("secret") != config.HUBSPOT_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    data = request.get_json(force=True, silent=True) or {}
    domains = [str(d).strip() for d in (data.get("domains") or []) if str(d).strip()]
    db = data.get("db")

    def _one(d):
        try:
            ov = semrush.domain_overview(d, db=db)
            return d, {"traffic": ov.get("organic_traffic", 0),
                       "keywords": ov.get("organic_keywords", 0)}
        except Exception as e:
            return d, {"error": str(e)[:100]}

    out = {}
    if domains:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for d, r in ex.map(_one, domains):
                out[d] = r
    return jsonify({"ok": True, "results": out})


@app.route("/debug/overview")
def debug_overview():
    # Діагностика: сира відповідь SemRush overview із колонками розподілу X0..XA.
    if request.args.get("secret") != config.HUBSPOT_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    domain = (request.args.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    db = request.args.get("db") or config.SEMRUSH_DB
    cols = "Dn,Rk,Or,Ot,Oc,Ad,At,Ac,X0,X1,X2,X3,X4,X5,X6,X7,X8,X9,XA"
    out = {"domain": domain, "db": db, "cols_requested": cols}
    for rtype in ("domain_ranks", "domain_rank"):
        try:
            raw = semrush._request({"type": rtype, "domain": domain,
                                    "database": db, "export_columns": cols})
            lines = raw.splitlines()
            out[rtype] = {"raw": raw[:600],
                          "header_fields": len(lines[0].split(";")) if lines else 0,
                          "value_fields": len(lines[1].split(";")) if len(lines) > 1 else 0}
        except Exception as e:
            out[rtype] = {"error": repr(e)[:300]}
    return jsonify(out)


@app.route("/healthz")
def healthz():
    return {"ok": True, "has_key": bool(config.SEMRUSH_API_KEY),
            "hubspot": bool(config.HUBSPOT_TOKEN), "manus": bool(config.MANUS_API_KEY)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=False)
