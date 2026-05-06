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


def test_create_endpoint_calls_sdk():
    client = MagicMock()
    ep = MagicMock()
    ep.id = "ep-123"
    ep.state = "PENDING"
    client.endpoints.create.return_value = ep
    provider = TogetherProvider(client=client)

    info = provider.create_endpoint(
        model="myorg/qwen-ft-abc",
        display_name="lynch-smoke",
        inactive_timeout_min=5,
    )

    assert info.endpoint_id == "ep-123"
    _, kwargs = client.endpoints.create.call_args
    assert kwargs["model"] == "myorg/qwen-ft-abc"
    assert kwargs["hardware"] == "1x_nvidia_h100_80gb_sxm"
    assert kwargs["autoscaling"] == {"min_replicas": 1, "max_replicas": 1}
    assert kwargs["inactive_timeout"] == 5


def test_wait_for_endpoint_ready_polls_until_started():
    client = MagicMock()
    states = ["PENDING", "PENDING", "STARTED"]
    side_effects = []
    for s in states:
        m = MagicMock()
        m.state = s
        side_effects.append(m)
    client.endpoints.retrieve.side_effect = side_effects
    provider = TogetherProvider(client=client)

    final_state = provider.wait_for_endpoint_ready("ep-123", poll_interval_s=0)

    assert final_state == "STARTED"
    assert client.endpoints.retrieve.call_count == 3


def test_delete_endpoint():
    client = MagicMock()
    provider = TogetherProvider(client=client)
    provider.delete_endpoint("ep-123")
    client.endpoints.delete.assert_called_once_with("ep-123")
