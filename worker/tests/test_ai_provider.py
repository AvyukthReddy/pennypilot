from worker.ai_provider import AIProvider, AIProviderConfig


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[dict] = []

    def create(self, model: str, messages: list[dict]):
        self.calls.append({"model": model, "messages": messages})
        return _FakeCompletion(self._reply)


class _FakeChat:
    def __init__(self, reply: str) -> None:
        self.completions = _FakeCompletions(reply)


class _FakeOpenAIClient:
    def __init__(self, reply: str) -> None:
        self.chat = _FakeChat(reply)


def test_complete_calls_configured_model_and_returns_content() -> None:
    client = _FakeOpenAIClient("hello")
    config = AIProviderConfig(base_url="https://example.com/v1", api_key="key", model="some/model")
    provider = AIProvider(config, client=client)

    result = provider.complete([{"role": "user", "content": "hi"}])

    assert result == "hello"
    assert client.chat.completions.calls[0]["model"] == "some/model"
    assert client.chat.completions.calls[0]["messages"] == [{"role": "user", "content": "hi"}]


def test_complete_handles_empty_content() -> None:
    client = _FakeOpenAIClient(None)
    config = AIProviderConfig(base_url="https://example.com/v1", api_key=None, model="m")
    provider = AIProvider(config, client=client)

    assert provider.complete([{"role": "user", "content": "hi"}]) == ""
