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


class EndpointInfo(BaseModel):
    """Together's chat.completions API routes by endpoint *name* (e.g.
    'kamalgs_07db/Qwen3-8B-lynch-smoke-bd77fafb-xxxxxx'), which is distinct
    from the FT *model* name passed at create time. Use `name` as the
    `model` parameter in inference calls."""

    endpoint_id: str
    name: str  # use this for chat.completions.create(model=...)
    model: str  # the FT model the endpoint serves
    state: str  # 'PENDING' | 'STARTING' | 'STARTED' | 'STOPPING' | 'STOPPED' | 'ERROR'


@runtime_checkable
class FineTuneProvider(Protocol):
    def upload_dataset(self, path: Path) -> str: ...
    def submit_job(
        self, train_file_id: str, cfg: TrainConfig, val_file_id: str | None = None
    ) -> str: ...
    def poll_job(self, job_id: str) -> JobStatus: ...
    def chat(self, model: str, messages: list[dict], **kwargs: Any) -> str: ...
    def create_endpoint(
        self, *, model: str, display_name: str, inactive_timeout_min: int
    ) -> EndpointInfo: ...
    def wait_for_endpoint_ready(
        self, endpoint_id: str, poll_interval_s: float = 15.0, timeout_s: float = 1200.0
    ) -> str: ...
    def delete_endpoint(self, endpoint_id: str) -> None: ...


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

    _DEFAULT_HARDWARE = "1x_nvidia_h100_80gb_sxm"

    def create_endpoint(
        self,
        *,
        model: str,
        display_name: str,
        inactive_timeout_min: int = 5,
    ) -> EndpointInfo:
        """Create a single-replica dedicated endpoint with idle auto-stop.

        Together rejects min_replicas=0, so we run min_replicas=1 and rely on
        `inactive_timeout` (minutes) to stop the endpoint when idle, plus an
        explicit delete_endpoint call when work is finished.
        """
        resp = self._client.endpoints.create(
            model=model,
            hardware=self._DEFAULT_HARDWARE,
            autoscaling={"min_replicas": 1, "max_replicas": 1},
            inactive_timeout=inactive_timeout_min,
            display_name=display_name,
        )
        return EndpointInfo(endpoint_id=resp.id, name=resp.name, model=model, state=resp.state)

    def wait_for_endpoint_ready(
        self,
        endpoint_id: str,
        poll_interval_s: float = 15.0,
        timeout_s: float = 1200.0,
    ) -> str:
        """Poll until endpoint state is STARTED. Raise on FAILED or timeout.

        Cold-start of an 8B model on H100 is typically 1-3 minutes; allow up to 20 min.
        """
        import time as _time

        deadline = _time.monotonic() + timeout_s
        while True:
            resp = self._client.endpoints.retrieve(endpoint_id)
            state = resp.state
            if state == "STARTED":
                return state
            if state in {"FAILED", "ERROR", "STOPPED"}:
                raise RuntimeError(f"endpoint {endpoint_id} entered terminal state: {state}")
            if _time.monotonic() > deadline:
                raise TimeoutError(
                    f"endpoint {endpoint_id} not ready after {timeout_s}s (last state={state})"
                )
            _time.sleep(poll_interval_s)

    def delete_endpoint(self, endpoint_id: str) -> None:
        self._client.endpoints.delete(endpoint_id)
