"""Vision intake — incidents often arrive as SCREENSHOTS (Grafana panels,
htop, error dialogs), not log files. A vision-capable OpenRouter model turns
an optional dashboard screenshot into text observations that enrich the
Classifier's input.

Image→data-URL handling adapted from my Eng Acc Day 5 multimodal assignment
(assignment_2_multimodal_messages.py).
"""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

from openai import OpenAI

PROMPT = """You are an SRE looking at a monitoring/terminal screenshot during \
an incident. Describe ONLY what is observable: metric names, values, thresholds \
breached, time ranges, error text, resource saturation. Note anomalies (spikes, \
flatlines, step changes) with their approximate timestamps. Do NOT diagnose or \
speculate about causes — observations only, as a compact bullet list."""


def _image_data_url(file_path: str | Path) -> str:
    path = Path(file_path)
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError(f"Not a supported image file: {path.name}")
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def observe_dashboard(image_path: str | Path) -> str:
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )
    model = os.environ.get("MODEL_VISION_ID") or os.environ.get(
        "MODEL_ID", "openai/gpt-4o-mini"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_data_url(image_path)},
                    },
                ],
            }
        ],
        max_tokens=1024,
        temperature=0.1,
    )
    return response.choices[0].message.content or ""
