"""Single LLM factory — all agents share one OpenRouter-backed client.
Every call reports its token usage into telemetry via a callback."""

import os

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

from . import telemetry

load_dotenv()


class _TokenCounter(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        usage = (response.llm_output or {}).get("token_usage") or {}
        if not usage:
            try:
                usage = response.generations[0][0].message.usage_metadata or {}
                usage = {
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                }
            except (AttributeError, IndexError):
                usage = {}
        telemetry.add(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ.get("MODEL_ID", "openai/gpt-4o-mini"),
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=temperature,
        callbacks=[_TokenCounter()],
    )
