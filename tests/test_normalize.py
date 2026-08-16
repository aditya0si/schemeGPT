"""normalize_question: rewrite for retrieval; never fail closed."""
from app import rag


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return _FakeResp(self.content)


def test_normalize_returns_cleaned_question(monkeypatch):
    fake = _FakeLLM("  What income support does PM-KISAN provide per year?  ")
    monkeypatch.setattr(rag, "get_llm", lambda: fake)
    out = rag.normalize_question("pm kisan me kitna paisa milta hai")
    assert out == "What income support does PM-KISAN provide per year?"


def test_normalize_falls_back_on_llm_error(monkeypatch):
    def boom():
        raise RuntimeError("groq down")

    monkeypatch.setattr(rag, "get_llm", boom)
    out = rag.normalize_question("pm kisan money?")
    assert out == "pm kisan money?"


def test_normalize_falls_back_on_empty_or_huge_output(monkeypatch):
    monkeypatch.setattr(rag, "get_llm", lambda: _FakeLLM("   "))
    assert rag.normalize_question("q") == "q"
    monkeypatch.setattr(
        rag, "get_llm", lambda: _FakeLLM("x" * 500)
    )
    assert rag.normalize_question("q") == "q"


def test_prompts_require_quotes_and_honesty():
    en = rag.SYSTEM_PROMPTS["en"]
    assert "quote" in en.lower()
    assert "directory_seed" in en
    hi = rag.SYSTEM_PROMPTS["hi"]
    assert "directory_seed" in hi
