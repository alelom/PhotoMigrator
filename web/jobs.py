"""
In-memory job store for web API.
Jobs are created when a task is started; status and logs are updated by the runner.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    mode: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    log_lines: List[str] = field(default_factory=list)
    error: str | None = None
    result_summary: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mode": self.mode,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "log_lines_count": len(self.log_lines),
            "error": self.error,
            "result_summary": self.result_summary,
        }


_jobs: dict[str, Job] = {}
_job_order: List[str] = []


def create_job(mode: str) -> Job:
    job_id = str(uuid.uuid4())
    now = datetime.utcnow()
    job = Job(
        id=job_id,
        mode=mode,
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    _jobs[job_id] = job
    _job_order.append(job_id)
    return job


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def list_jobs(limit: int = 50) -> List[Job]:
    order = _job_order[-limit:] if limit else _job_order
    order = order[::-1]
    return [_jobs[jid] for jid in order if jid in _jobs]


def update_job_status(job_id: str, status: JobStatus, error: str | None = None, result_summary: str | None = None) -> None:
    job = _jobs.get(job_id)
    if job:
        job.status = status
        job.updated_at = datetime.utcnow()
        if error is not None:
            job.error = error
        if result_summary is not None:
            job.result_summary = result_summary


def append_job_log(job_id: str, line: str) -> None:
    job = _jobs.get(job_id)
    if job:
        job.log_lines.append(line)
        job.updated_at = datetime.utcnow()
