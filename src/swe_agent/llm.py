"""One client for every OpenAI-compatible endpoint.

Ollama, OpenRouter, GitHub Models and Gemini all expose an OpenAI-compatible
API, so switching providers only means changing base_url / api_key / model.
"""

import os
from dataclasses import dataclass

from .cache import ResponseCache, cache_key
from .costs import CostTracker


@dataclass
class LLMConfig:
    model: str
    base_url: str = "http://localhost:11434/v1"  # Ollama default
    api_key_env: str = "LLM_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 1024


class LLM:
    def __init__(self, config: LLMConfig, cache: ResponseCache | None, tracker: CostTracker):
        from openai import OpenAI

        self.config = config
        self.cache = cache
        self.tracker = tracker
        self.client = OpenAI(base_url=config.base_url, api_key=os.environ.get(config.api_key_env, "ollama"))

    def chat(self, messages: list[dict]) -> str:
        params = {"temperature": self.config.temperature, "max_tokens": self.config.max_tokens}
        key = cache_key(self.config.model, messages, params)
        if self.cache and (hit := self.cache.get(key)):
            self.tracker.record(self.config.model, hit["input_tokens"], hit["output_tokens"], cached=True)
            return hit["content"]

        resp = self.client.chat.completions.create(model=self.config.model, messages=messages, **params)
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        in_tok, out_tok = (usage.prompt_tokens, usage.completion_tokens) if usage else (0, 0)
        self.tracker.record(self.config.model, in_tok, out_tok, cached=False)
        if self.cache:
            self.cache.put(key, {"content": content, "input_tokens": in_tok, "output_tokens": out_tok})
        return content
