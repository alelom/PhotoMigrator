"""
Runs PhotoMigrator execution modes with request-scoped ARGS and captures logs to a job.
Must run in a dedicated thread; only one job should run at a time (global state).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure project root and src are on path before importing Core/Features
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Lazy imports of Core/Features inside run_mode to avoid importing before path is set
# and to keep web dependencies optional until runner is used


def _default_args() -> dict[str, Any]:
    """Build default ARGS dict matching ArgsParser defaults (kebab-case keys)."""
    return {
        "configuration-file": os.environ.get("PHOTOMIGRATOR_CONFIG_PATH", "") or str(PROJECT_ROOT / "Config.ini"),
        "no-request-user-confirmation": True,
        "no-log-file": False,
        "log-level": "info",
        "log-format": "log",
        "date-separator": "-",
        "range-separator": "--",
        "foldername-albums": "",
        "foldername-no-albums": "",
        "foldername-logs": "",
        "foldername-duplicates-output": "",
        "foldername-extracted-dates": "",
        "exec-gpth-tool": "",
        "exec-exif-tool": "",
        "input-folder": "",
        "output-folder": "",
        "client": "google-takeout",
        "account-id": 1,
        "filter-from-date": None,
        "filter-to-date": None,
        "filter-by-type": None,
        "filter-by-country": None,
        "filter-by-city": None,
        "filter-by-person": None,
        "albums-folders": [],
        "remove-albums-assets": False,
        "source": "",
        "target": "",
        "move-assets": False,
        "dashboard": True,
        "parallel-migration": True,
        "google-takeout": "",
        "google-output-folder-suffix": "processed",
        "google-albums-folders-structure": "flatten",
        "google-no-albums-folders-structure": "year/month",
        "google-ignore-check-structure": False,
        "google-no-symbolic-albums": False,
        "google-remove-duplicates-files": False,
        "google-rename-albums-folders": False,
        "google-skip-extras-files": False,
        "google-skip-move-albums": False,
        "google-skip-gpth-tool": False,
        "google-skip-preprocess": False,
        "google-skip-postprocess": False,
        "google-keep-takeout-folder": False,
        "show-gpth-info": True,
        "show-gpth-errors": True,
        "gpth-no-log": False,
        "upload-albums": "",
        "download-albums": [],
        "upload-all": "",
        "download-all": "",
        "rename-albums": [],
        "remove-albums": "",
        "remove-all-albums": False,
        "remove-all-assets": False,
        "remove-empty-albums": False,
        "remove-duplicates-albums": False,
        "merge-duplicates-albums": False,
        "remove-orphan-assets": False,
        "one-time-password": False,
        "fix-symlinks-broken": "",
        "rename-folders-content-based": "",
        "find-duplicates": ["list", ""],
        "process-duplicates": "",
        "google-input-zip-folder": None,
        "AUTOMATIC-MIGRATION": None,
        "duplicates-folders": [],
        "duplicates-action": "list",
    }


def _merge_api_args(default: dict, api_args: dict) -> dict:
    """Merge API payload (kebab-case) into default; only set keys that are in api_args."""
    out = dict(default)
    for k, v in api_args.items():
        if k in out:
            out[k] = v
    return out


class _JobLogHandler(logging.Handler):
    """Logging handler that appends to a job's log buffer."""

    def __init__(self, append_callback):
        super().__init__()
        self._append = append_callback

    def emit(self, record):
        try:
            msg = self.format(record)
            self._append(msg)
        except Exception:
            self.handleError(record)


def run_mode(job_id: str, mode: str, api_body: dict[str, Any]) -> None:
    """
    Run a single PhotoMigrator mode with ARGS built from api_body.
    Updates job status and appends log lines via jobs.append_job_log(job_id, line).
    """
    from web import jobs

    jobs.update_job_status(job_id, jobs.JobStatus.RUNNING)

    try:
        import Core.GlobalVariables as GV
        from Core.ArgsParser import checkArgs
        from Core.GlobalFunctions import set_GLOBAL_VARIABLES, set_HELP_TEXTS, set_LOGGER
        from Core.ExecutionModes import mode_google_takeout, mode_AUTOMATIC_MIGRATION

        # Build ARGS: default + API body (keys already kebab-case from schemas.api_to_args)
        default = _default_args()
        ARGS = _merge_api_args(default, api_body)

        # Normalize list types for parser compatibility
        if "download-albums" in api_body and isinstance(ARGS.get("download-albums"), list):
            pass  # already list
        if "find-duplicates" in api_body:
            fd = ARGS.get("find-duplicates")
            if isinstance(fd, list):
                ARGS["find-duplicates"] = fd
            else:
                ARGS["find-duplicates"] = ["list", fd] if fd else ["list", ""]

        # Mock parser that raises instead of exit() so we can return 400
        class MockParser:
            def error(self, msg):
                raise ValueError(msg)

        try:
            checkArgs(ARGS, MockParser())
        except ValueError as e:
            jobs.update_job_status(job_id, jobs.JobStatus.FAILED, error=str(e))
            return

        # Set globals and init (same order as PhotoMigrator.PhotoMigrator)
        GV.ARGS = ARGS
        set_GLOBAL_VARIABLES()
        set_LOGGER()
        set_HELP_TEXTS()

        # Capture logs to job
        def append_log(line: str):
            jobs.append_job_log(job_id, line)

        handler = _JobLogHandler(append_log)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        GV.LOGGER.addHandler(handler)

        try:
            if mode == "google-takeout":
                mode_google_takeout(user_confirmation=False)
            elif mode == "automatic-migration":
                mode_AUTOMATIC_MIGRATION(show_gpth_info=ARGS.get("show-gpth-info", True))
            else:
                raise ValueError(f"Unknown mode: {mode}")
        finally:
            GV.LOGGER.removeHandler(handler)

        jobs.update_job_status(job_id, jobs.JobStatus.DONE, result_summary="Completed successfully")

    except Exception as e:
        from web import jobs as j
        j.append_job_log(job_id, f"Error: {e}")
        j.update_job_status(job_id, j.JobStatus.FAILED, error=str(e))
