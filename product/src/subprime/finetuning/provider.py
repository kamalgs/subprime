"""Fine-tune provider abstraction + Together AI implementation.

The protocol exists so we can later swap in a self-hosted QLoRA provider
(Lambda Cloud + Unsloth/TRL) without touching harvest/curate/format/train.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class TrainConfig(BaseModel):
    base_model: str = "Qwen/Qwen3-8B"
    n_epochs: int = 3
    learning_rate: float = 1e-4
    lora_rank: int = 16
    lora_alpha: int = 32
    suffix: str = ""
    warmup_ratio: float = 0.0


class JobStatus(BaseModel):
    state: str  # 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
    output_model: str | None = None
    raw: dict[str, Any] = {}


@runtime_checkable
class FineTuneProvider(Protocol):
    def upload_dataset(self, path: Path) -> str: ...
    def submit_job(
        self, train_file_id: str, cfg: TrainConfig, val_file_id: str | None = None
    ) -> str: ...
    def poll_job(self, job_id: str) -> JobStatus: ...
    def chat(self, model: str, messages: list[dict], **kwargs: Any) -> str: ...


class TogetherProvider:
    """Thin wrapper around the `together` SDK."""

    def __init__(self, client: Any | None = None, api_key: str | None = None):
        if client is not None:
            self._client = client
            return
        from together import Together  # local import keeps `together` optional in tests

        key = api_key or os.environ.get("TOGETHER_API_KEY")
        if not key:
            raise RuntimeError("TOGETHER_API_KEY not set")
        self._client = Together(api_key=key)

    def upload_dataset(self, path: Path) -> str:
        resp = self._client.files.upload(str(path), purpose="fine-tune", check=True)
        return resp.id

    def submit_job(
        self,
        train_file_id: str,
        cfg: TrainConfig,
        val_file_id: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = dict(
            training_file=train_file_id,
            model=cfg.base_model,
            n_epochs=cfg.n_epochs,
            learning_rate=cfg.learning_rate,
            lora=True,
            lora_r=cfg.lora_rank,
            lora_alpha=cfg.lora_alpha,
            warmup_ratio=cfg.warmup_ratio,
            suffix=cfg.suffix,
            train_on_inputs="auto",
            n_checkpoints=1,
        )
        if val_file_id:
            kwargs["validation_file"] = val_file_id
        resp = self._client.fine_tuning.create(**kwargs)
        return resp.id

    def poll_job(self, job_id: str) -> JobStatus:
        resp = self._client.fine_tuning.retrieve(job_id)
        output = getattr(resp, "output_name", None) or getattr(resp, "model_output_name", None)
        raw = resp.model_dump() if hasattr(resp, "model_dump") else {}
        return JobStatus(state=resp.status, output_model=output, raw=raw)

    def chat(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(model=model, messages=messages, **kwargs)
        return resp.choices[0].message.content
