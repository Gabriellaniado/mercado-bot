from types import SimpleNamespace

import pytest

from bot import summarize

ENTRY = {"symbol": "INTC", "name": "Intel", "ret_pct": -28.6, "tag": "[CEDEAR]"}
CFG = {"model": "modelo", "max_tokens": 100}


def test_prompt_includes_headlines_and_marks_missing_ones():
    news = {"INTC": [{"title": "Cae Intel", "source": "CNBC"}]}
    other = {**ENTRY, "symbol": "AMD", "name": "AMD"}
    prompt = summarize.build_prompt([ENTRY, other], news)
    assert "Cae Intel (CNBC)" in prompt
    assert "sin titulares de fuentes confiables" in prompt


def test_no_summary_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert summarize.summarize([ENTRY], {}, CFG) is None


def test_no_summary_without_entries(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert summarize.summarize([], {}, CFG) is None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    fake = SimpleNamespace(messages=SimpleNamespace())
    monkeypatch.setattr(summarize.anthropic, "Anthropic", lambda api_key: fake)
    return fake


def test_summary_joins_only_text_blocks(client):
    blocks = [SimpleNamespace(type="text", text=" Resumen "), SimpleNamespace(type="other")]
    client.messages.create = lambda **kwargs: SimpleNamespace(content=blocks)
    assert summarize.summarize([ENTRY], {}, CFG) == "Resumen"


def test_summary_failure_does_not_stop_the_report(client):
    def fail(**kwargs):
        raise RuntimeError("caído")

    client.messages.create = fail
    assert summarize.summarize([ENTRY], {}, CFG) is None
