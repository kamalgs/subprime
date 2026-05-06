"""Tests for finetuning.provider — TogetherProvider with mocked SDK."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from subprime.finetuning.provider import (
    JobStatus,
    TogetherProvider,
    TrainConfig,
)


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.files.upload.return_value = MagicMock(id="file-abc")
    client.fine_tuning.create.return_value = MagicMock(id="ft-job-xyz")
    retrieve = MagicMock()
    retrieve.id = "ft-job-xyz"
    retrieve.status = "completed"
    retrieve.output_name = "myorg/Qwen3-8B-lynch-ft-job-xyz"
    retrieve.model_dump = lambda: {"id": "ft-job-xyz", "status": "completed"}
    client.fine_tuning.retrieve.return_value = retrieve
    return client


def test_upload_dataset_calls_sdk(tmp_path: Path):
    jsonl = tmp_path / "t.jsonl"
    jsonl.write_text('{"messages": []}\n')
    client = _mock_client()
    provider = TogetherProvider(client=client)

    file_id = provider.upload_dataset(jsonl)

    assert file_id == "file-abc"
    client.files.upload.assert_called_once()
    args, kwargs = client.files.upload.call_args
    assert kwargs.get("purpose") == "fine-tune"


def test_submit_job_passes_lora_hparams():
    client = _mock_client()
    provider = TogetherProvider(client=client)
    cfg = TrainConfig(
        base_model="Qwen/Qwen3-8B",
        n_epochs=3,
        learning_rate=1e-4,
        suffix="lynch-smoke",
    )

    job_id = provider.submit_job(train_file_id="file-abc", cfg=cfg)

    assert job_id == "ft-job-xyz"
    _, kwargs = client.fine_tuning.create.call_args
    assert kwargs["model"] == "Qwen/Qwen3-8B"
    assert kwargs["lora"] is True
    assert kwargs["n_epochs"] == 3
    assert kwargs["suffix"] == "lynch-smoke"


def test_poll_job_returns_status():
    client = _mock_client()
    provider = TogetherProvider(client=client)

    status = provider.poll_job("ft-job-xyz")

    assert isinstance(status, JobStatus)
    assert status.state == "completed"
    assert status.output_model == "myorg/Qwen3-8B-lynch-ft-job-xyz"


def test_chat_invokes_completions_endpoint():
    client = _mock_client()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="hello"))]
    )
    provider = TogetherProvider(client=client)

    out = provider.chat(
        model="myorg/foo",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert out == "hello"
    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["model"] == "myorg/foo"
