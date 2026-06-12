"""Run telemetry — thread-safe token counter across every LLM call in a run
(classifier, per-incident remediation branches, cookbook, vision)."""

from __future__ import annotations

import threading

# gpt-4o-mini via OpenRouter (USD per 1M tokens) — display estimate only.
PROMPT_RATE = 0.15
COMPLETION_RATE = 0.60

_lock = threading.Lock()
_prompt = 0
_completion = 0
_calls = 0


def reset() -> None:
    global _prompt, _completion, _calls
    with _lock:
        _prompt = _completion = _calls = 0


def add(prompt_tokens: int, completion_tokens: int) -> None:
    global _prompt, _completion, _calls
    with _lock:
        _prompt += int(prompt_tokens or 0)
        _completion += int(completion_tokens or 0)
        _calls += 1


def snapshot() -> dict:
    with _lock:
        cost = (_prompt * PROMPT_RATE + _completion * COMPLETION_RATE) / 1_000_000
        return {
            "calls": _calls,
            "prompt": _prompt,
            "completion": _completion,
            "total": _prompt + _completion,
            "cost_usd": round(cost, 4),
        }
