from dataclasses import dataclass

from openai import OpenAI


@dataclass
class AIProviderConfig:
    base_url: str
    api_key: str | None
    model: str


class AIProvider:
    """Thin wrapper around an OpenAI-compatible chat completions endpoint.
    Base URL, API key, and model are all configuration (see
    worker.config.default_ai_provider_config) — swapping providers or
    benchmarking a different model is a config change, never a code change
    to the extraction pipeline that calls this."""

    def __init__(self, config: AIProviderConfig, client: OpenAI | None = None):
        self.model = config.model
        self.client = client or OpenAI(base_url=config.base_url, api_key=config.api_key)

    def complete(self, messages: list[dict]) -> str:
        completion = self.client.chat.completions.create(model=self.model, messages=messages)
        return completion.choices[0].message.content or ""
