"""
PhotoMigrator web interface: FastAPI app, job queue worker, and routes.
Run from project root: uv run --group web python -m web.main
"""
from __future__ import annotations

import os
import queue
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from web import jobs
from web.runner import run_mode
from web.schemas import (
    GoogleTakeoutRequest,
    AutomaticMigrationRequest,
    api_to_args,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Job queue: (job_id, mode, args_dict)
_job_queue: queue.Queue = queue.Queue()


def _worker():
    while True:
        try:
            item = _job_queue.get()
            if item is None:
                break
            job_id, mode, args_dict = item
            run_mode(job_id, mode, args_dict)
        except Exception:
            pass
        finally:
            _job_queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    yield
    _job_queue.put(None)


app = FastAPI(title="PhotoMigrator Web", lifespan=lifespan)

if TEMPLATES_DIR.exists():
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
else:
    templates = None

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- API ---

@app.post("/api/jobs/google-takeout")
def start_google_takeout(body: GoogleTakeoutRequest):
    """Start a Google Takeout processing job."""
    job = jobs.create_job("google-takeout")
    args = api_to_args("google-takeout", body.model_dump())
    args["google-takeout"] = body.takeout_folder
    if body.output_folder:
        args["output-folder"] = body.output_folder
    _job_queue.put((job.id, "google-takeout", args))
    return {"job_id": job.id}


@app.post("/api/jobs/automatic-migration")
def start_automatic_migration(body: AutomaticMigrationRequest):
    """Start an automatic migration job (source -> target)."""
    job = jobs.create_job("automatic-migration")
    args = api_to_args("automatic-migration", body.model_dump())
    args["source"] = body.source
    args["target"] = body.target
    _job_queue.put((job.id, "automatic-migration", args))
    return {"job_id": job.id}


# --- Form submit (HTML forms post here; redirect to job page) ---

@app.post("/jobs/google-takeout")
def form_google_takeout(
    takeout_folder: str = Form(..., alias="takeout_folder"),
    output_folder: str = Form(""),
    google_skip_gpth_tool: str = Form(""),
):
    job = jobs.create_job("google-takeout")
    args = _default_args()
    args["google-takeout"] = takeout_folder
    if output_folder:
        args["output-folder"] = output_folder
    args["google-skip-gpth-tool"] = (google_skip_gpth_tool or "").lower() in ("true", "1", "yes")
    _job_queue.put((job.id, "google-takeout", args))
    return RedirectResponse(url=f"/job/{job.id}", status_code=303)


@app.post("/jobs/automatic-migration")
def form_automatic_migration(
    source: str = Form(..., alias="source"),
    target: str = Form(..., alias="target"),
    move_assets: str = Form(""),
    dashboard: str = Form(""),
    parallel_migration: str = Form(""),
):
    def b(v): return (v or "").lower() in ("true", "1", "yes")
    job = jobs.create_job("automatic-migration")
    args = _default_args()
    args["source"] = source
    args["target"] = target
    args["move-assets"] = b(move_assets)
    args["dashboard"] = b(dashboard) if dashboard != "" else True
    args["parallel-migration"] = b(parallel_migration) if parallel_migration != "" else True
    _job_queue.put((job.id, "automatic-migration", args))
    return RedirectResponse(url=f"/job/{job.id}", status_code=303)


def _default_args():
    from web.runner import _default_args as da
    return da()


@app.get("/api/jobs")
def list_jobs_route(limit: int = 50):
    """List recent jobs."""
    return [j.to_dict() for j in jobs.list_jobs(limit=limit)]


@app.get("/api/jobs/{job_id}")
def get_job_api(job_id: str):
    """Get job status and summary."""
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/logs")
def get_job_logs(job_id: str):
    """Get full log lines for a job (for polling)."""
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "lines": job.log_lines}


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the web UI."""
    if templates is None:
        return HTMLResponse(
            "<h1>PhotoMigrator Web</h1><p>Templates not found. Add web/templates/.</p>",
            status_code=200,
        )
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: str):
    """Job detail page with log viewer."""
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if templates is None:
        return HTMLResponse(f"<pre>Job {job_id}\nStatus: {job.status}\n\n" + "\n".join(job.log_lines) + "</pre>")
    return templates.TemplateResponse(
        "job_detail.html",
        {"request": request, "job": job, "job_id": job_id},
    )


def _config_path() -> Path:
    """Path to Config.ini (env PHOTOMIGRATOR_CONFIG_PATH or project root)."""
    path = os.environ.get("PHOTOMIGRATOR_CONFIG_PATH", "")
    if path:
        return Path(path)
    return PROJECT_ROOT / "Config.ini"


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request, saved: str = ""):
    """Configuration page: view and edit Config.ini with structured form fields."""
    from web.config_ini import parse_config_with_schema, form_field_name

    path = _config_path()
    sections = parse_config_with_schema(path)
    writable = path.exists() and os.access(path, os.W_OK)
    if not path.exists() and path.parent.exists() and os.access(path.parent, os.W_OK):
        writable = True
    if templates is None:
        return HTMLResponse(
            f"<h1>Configuration</h1><p>Path: {path}</p><p>{len(sections)} sections</p>",
            status_code=200,
        )
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "config_path": str(path),
            "sections": sections,
            "form_field_name": form_field_name,
            "saved": saved == "1",
            "writable": writable,
        },
    )


@app.post("/config")
async def config_save(request: Request):
    """Save Config.ini from structured form (all form fields with prefix v||)."""
    from web.config_ini import build_ini_from_form, FORM_SEP

    path = _config_path()
    if not path.parent.exists():
        raise HTTPException(status_code=500, detail="Config directory does not exist")
    form = await request.form()
    form_data = {k: (v if isinstance(v, str) else "") for k, v in form.items() if k.startswith("v" + FORM_SEP)}
    content = build_ini_from_form(form_data)
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot write config: {e}")
    return RedirectResponse(url="/config?saved=1", status_code=303)


def run_web(host: str = "0.0.0.0", port: int = 8000):
    """Entry point for running the web server (e.g. uv run python -m web.main)."""
    import uvicorn
    os.chdir(PROJECT_ROOT)
    uvicorn.run("web.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_web()
