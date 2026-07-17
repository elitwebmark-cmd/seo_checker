"""Веб-інтерфейс: авторизація -> список сайтів -> прогрес -> результати."""
import os, uuid, threading, concurrent.futures, functools, time, logging
from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, session)

import qualify, config

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


def _safe_qualify(domain, do_onpage):
    try:
        return qualify.qualify(domain, do_onpage=do_onpage)
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


def _process_job(job_id, domains, do_onpage):
    log.info("job %s START: %d domain(s), onpage=%s", job_id, len(domains), do_onpage)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(_safe_qualify, d, do_onpage): d for d in domains}
            try:
                for fut in concurrent.futures.as_completed(futs, timeout=JOB_TIMEOUT):
                    d = futs[fut]
                    res = fut.result()
                    log.info("job %s: %s -> %s", job_id, d, res.get("verdict"))
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


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    domains = _parse_domains(request.form.get("domains", ""))
    do_onpage = request.form.get("onpage") == "on"
    if not domains:
        return redirect(url_for("index"))
    _prune_jobs()
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"total": len(domains), "done": 0, "results": [],
                        "status": "running", "do_onpage": do_onpage,
                        "started": time.time(), "finished": None}
    threading.Thread(target=_process_job, args=(job_id, domains, do_onpage),
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
                           do_onpage=job["do_onpage"], bot_url=config.TELEGRAM_BOT_URL)


@app.route("/api/analyze", methods=["POST"])
@login_required
def api_analyze():
    data = request.get_json(force=True, silent=True) or {}
    raw = data.get("domains")
    raw = "\n".join(raw) if isinstance(raw, list) else str(raw or "")
    domains = _parse_domains(raw)
    do_onpage = bool(data.get("onpage", True))
    out = []
    if domains:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(_safe_qualify, d, do_onpage): d for d in domains}
            for fut in concurrent.futures.as_completed(futs):
                out.append(fut.result())
        out.sort(key=lambda r: r.get("score", 0), reverse=True)
    return jsonify({"results": out})


@app.route("/healthz")
def healthz():
    return {"ok": True, "has_key": bool(config.SEMRUSH_API_KEY)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=False)
