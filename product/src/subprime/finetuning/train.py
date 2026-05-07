"""Run a fine-tune job end-to-end and record artifacts."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from subprime.finetuning.provider import FineTuneProvider, JobStatus, TrainConfig


_TERMINAL_OK = {"completed"}
_TERMINAL_FAIL = {"failed", "cancelled", "error"}


class RunArtifacts(BaseModel):
    job_id: str
    output_model: str
    train_path: str
    val_path: str | None = None
    config: TrainConfig
    started_at: datetime
    finished_at: datetime
    final_status: JobStatus


def run_job(
    *,
    provider: FineTuneProvider,
    train_path: Path,
    cfg: TrainConfig,
    out_dir: Path,
    val_path: Path | None = None,
    poll_interval_s: float = 30.0,
) -> RunArtifacts:
    """Upload, submit, poll. Persist artifacts.json and return RunArtifacts."""
    started = datetime.utcnow()
    train_id = provider.upload_dataset(train_path)
    val_id = provider.upload_dataset(val_path) if val_path else None
    job_id = provider.submit_job(train_id, cfg, val_file_id=val_id)

    while True:
        status = provider.poll_job(job_id)
        if status.state in _TERMINAL_OK:
            break
        if status.state in _TERMINAL_FAIL:
            raise RuntimeError(f"fine-tune job {job_id} failed: state={status.state}")
        time.sleep(poll_interval_s)

    if not status.output_model:
        raise RuntimeError(f"job {job_id} completed but no output_model returned")

    finished = datetime.utcnow()
    artifacts = RunArtifacts(
        job_id=job_id,
        output_model=status.output_model,
        train_path=str(train_path),
        val_path=str(val_path) if val_path else None,
        config=cfg,
        started_at=started,
        finished_at=finished,
        final_status=status,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "artifacts.json").write_text(artifacts.model_dump_json(indent=2))
    return artifacts
