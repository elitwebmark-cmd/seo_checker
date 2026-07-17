"""Веб-інтерфейс: авторизація -> список сайтів -> прогрес -> результати."""
import os, uuid, threading, concurrent.futures, functools, time
from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, session, abort)

import qualify, config

app = Flask(__name__, template_folder=".")
app.secret_key = config.SECRET_KEY
MAX_DOMAINS = int(os.getenv("MAX_DOMAINS", "100"))
WORKERS = int(os.getenv("WORKERS", "6"))

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
            nxt = request.args.get("next") or url_for("index")
            return redirect(nxt)
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


def _safe_qualify(domain, do_onpage):
    try:
        return qualify.qualify(domain, do_onpage=do_onpage)
    except Exception as e:
        return {"domain": domain, "verdict": "ПОМИЛКА", "color": "gray",
                "score": -1, "error": str(e)[:200], "reasons": [], "metrics": {},
                "dotisk_queries": []}


def _process_job(job_id, domains, do_onpage):
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_safe_qualify, d, do_onpage): d for d in domains}
        for fut in concurrent.futures.as_completed(futs):
            res = fut.result()
            with JOBS_LOCK:
                j = JOBS.get(job_id)
                if j is None:
                    return
                j["results"].append(res)
                j["done"] += 1
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if j:
            j["results"].sort(key=lambda r: r.get("score", 0), reverse=True)
            j["status"] = "done"
            j["finished"] = time.time()


def _prune_jobs():
    now = time.time()
    with JOBS_LOCK:
        old = [k for k, v in JOBS.items()
               if v.get("finished") and now - v["finished"] > 3600]
        for k in old:
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
    results_list = []
    if domains:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(_safe_qualify, d, do_onpage): d for d in domains}
            for fut in concurrent.futures.as_completed(futs):
                results_list.append(fut.result())
        results_list.sort(key=lambda r: r.get("score", 0), reverse=True)
    return jsonify({"results": results_list})


@app.route("/healthz")
def healthz():
    return {"ok": True, "has_key": bool(config.SEMRUSH_API_KEY)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=False)
