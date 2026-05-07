"""Tests for finetuning.train — orchestration with mocked provider."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from subprime.finetuning.provider import JobStatus, TrainConfig
from subprime.finetuning.train import RunArtifacts, run_job


def _provider(states: list[str], output_model: str = "myorg/foo") -> MagicMock:
    p = MagicMock()
    p.upload_dataset.return_value = "file-abc"
    p.submit_job.return_value = "ft-job-xyz"
    p.poll_job.side_effect = [
        JobStatus(state=s, output_model=output_model if s == "completed" else None) for s in states
    ]
    return p


def test_run_job_polls_until_completed(tmp_path: Path):
    train = tmp_path / "t.jsonl"
    train.write_text('{"messages": []}\n')
    provider = _provider(["pending", "running", "completed"])
    cfg = TrainConfig(suffix="smoke")

    artifacts = run_job(
        provider=provider,
        train_path=train,
        cfg=cfg,
        out_dir=tmp_path / "out",
        poll_interval_s=0,
    )

    assert isinstance(artifacts, RunArtifacts)
    assert artifacts.output_model == "myorg/foo"
    assert artifacts.job_id == "ft-job-xyz"
    assert provider.poll_job.call_count == 3
    assert (tmp_path / "out" / "artifacts.json").exists()


def test_run_job_raises_on_failure(tmp_path: Path):
    train = tmp_path / "t.jsonl"
    train.write_text("{}\n")
    provider = _provider(["pending", "failed"])
    cfg = TrainConfig(suffix="smoke")

    with pytest.raises(RuntimeError, match="failed"):
        run_job(
            provider=provider,
            train_path=train,
            cfg=cfg,
            out_dir=tmp_path / "out",
            poll_interval_s=0,
        )
