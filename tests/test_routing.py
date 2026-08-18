"""Model routing: fast model for cheap tasks, strong model for answers."""

from types import SimpleNamespace

from app import rag
from app.config import settings


class _Capturing:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.instances.append(kwargs)

    def invoke(self, messages):  # used by the routing spy below
        return SimpleNamespace(content="clean query")


def test_get_llm_routes_roles_to_models(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "dummy")
    monkeypatch.setattr(rag, "ChatGroq", _Capturing)
    _Capturing.instances = []

    rag.get_llm()                       # answer role -> strong model, 1024
    rag.get_llm("fast", max_tokens=160)  # fast role -> cheap model, 160

    assert _Capturing.instances[0]["model"] == settings.groq_model
    assert _Capturing.instances[0]["max_tokens"] == 1024
    assert _Capturing.instances[1]["model"] == settings.groq_fast_model
    assert _Capturing.instances[1]["max_tokens"] == 160


def test_get_llm_fast_uses_configured_fast_model(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "dummy")
    monkeypatch.setattr(settings, "groq_fast_model", "custom-fast")
    monkeypatch.setattr(rag, "ChatGroq", _Capturing)
    _Capturing.instances = []
    rag.get_llm("fast")
    assert _Capturing.instances[0]["model"] == "custom-fast"


def test_normalize_question_uses_fast_role_and_tight_budget(monkeypatch):
    calls = []

    class _LLM:
        def invoke(self, messages):
            return SimpleNamespace(content="clean")

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return _LLM()

    monkeypatch.setattr(rag, "get_llm", spy)
    assert rag.normalize_question("raw question") == "clean"
    assert calls and calls[0][0][0] == "fast"
    assert calls[0][1]["max_tokens"] == 160
